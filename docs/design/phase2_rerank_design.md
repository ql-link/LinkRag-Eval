# 阶段 2 · 重排层 — 设计文档

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase0_design.md](phase0_design.md)（抽象/模型）、[phase1_design.md](phase1_design.md)（检索层，本层上游产出）、[technical_design.md](technical_design.md) §一/§六（rerank 口径）
> 范围：在检索层闭环之上叠加**重排评估**——量化精排相对纯 RRF 顺序的真实增益，模块 16–17（`rerank_adapter` + `metrics/rerank`）。
> 前置：检索层（阶段 1）已可跑；冻结评测租户**须已配置 RERANK 模型**（见 §六）。

---

## 一、结论先行

重排是 best-effort 增强、已知不可用时降级为 RRF 顺序。评估的核心问题不是"重排后指标多少"，而是"**重排相对纯 RRF 到底有没有起效、起效多少**"。两条决策：

1. **同一 run 内同时产出两种顺序，在同一候选集上对比。** rerank 生效顺序 vs `degrade_to_rrf_order` 顺序，二者必须建立在**同一份"已过滤正文的候选集"**上，否则对比不成立。适配器显式回填正文、共享候选集，让两序可比。
2. **指标输出"绝对值 + 对 RRF 的增量 Δ"，并如实报告 `rerank_applied` 率。** ΔNDCG@k / ΔMRR 才是"精排把对的排得更前"的直接信号；同时报告本轮多少样本真正走了 rerank（而非降级），避免拿大量降级样本稀释出的"零增益"误判。

依赖方向更干净：`PostRecallReranker()` 可直接默认构造（`content_fetcher=fetch_chunk_contents`、`model_resolver=aresolve_user_model` 均在 `core`），**重排适配器 core-only，无需像召回那样依赖 application provider**。

---

## 二、被依赖的生产接缝

| 用途 | 入口 | 关键语义 |
| --- | --- | --- |
| 重排 | `PostRecallReranker.rerank(RerankRequest) -> RerankResponse` | `RerankRequest(query, user_id, hits: list[RecallHit], top_n=None, contents=None)`；`RerankResponse(query, hits: list[RerankedHit], rerank_applied: bool, elapsed_ms)` |
| 正文回填 | `fetch_chunk_contents(chunk_ids, user_id)` | 只返回本用户 ACTIVE 非空正文；查不到的 chunk 不参与 rerank |
| 降级顺序（口径单一来源） | `degrade_to_rrf_order(content_present_hits, top_n)` | 入参须为**已过滤无正文**的候选；按 RRF 序输出 `RerankedHit`（`rerank_score=None`），截断 `top_n` |
| RERANK 模型解析 | `aresolve_user_model(user_id, capability="RERANK", allow_system_fallback=False)` | **硬失败点**：未配置/provider 不支持 → 抛异常、不降级 |

`RerankedHit` 字段：`chunk_id` / `doc_id` / `dataset_id` / `fused_score` / `scores` / `rerank_score`(降级或无分 tail 为 `None`) / `rerank_rank`。

**降级触发**（`rerank_applied=False`）：模型调用异常、或返回索引不可用。两种情形 reranker 都回 `degrade_to_rrf_order`。

---

## 三、模块结构

```
src/evaluation/
├── adapters/
│   └── rerank_adapter.py    # ⑯ 实现 Evaluable(layer=RERANK)：同 run 产 rerank 序 + RRF 序
└── metrics/
    └── rerank.py            # ⑰ 复用 ndcg/mrr：绝对值 + 对 RRF 增量 Δ + rerank_applied 率
```

runner / reporter / snapshot 复用阶段 1，无需新增（snapshot 已含 `rerank_top_n` 字段）。

---

## 四、重排适配器（⑯ `rerank_adapter.py`）

### 4.1 上游消费：从 `upstream.raw` 取真实 `RecallHit`

rerank 需要 `list[RecallHit]`（含 `scores` 等元信息），而上游 `StageOutput.ranked` 是归一化的 `RankedHit`（已丢 `scores` 细节）。故适配器读**上游 `StageOutput.raw`**（即检索层的 `RecallResponse`）取原始 `RecallHit`。这是 adapter 层对 `raw` 的合法使用——phase0 约定"`raw` 供适配器/调试，**指标**不依赖它"，适配器不在此列。

### 4.2 同 run 双序，共享同一候选集

```python
class RerankEvaluable:
    layer = Layer.RERANK
    def __init__(self, reranker: PostRecallReranker, top_n: int): ...
    async def run(self, sample: Sample, *, upstream: StageOutput) -> StageOutput:
        recall_hits = upstream.raw.hits                      # list[RecallHit]，RRF 序
        # 1. 回填正文一次，两序共享 → 保证候选集完全一致
        contents = await fetch_chunk_contents(
            [h.chunk_id for h in recall_hits], sample.user_id)
        content_present = [h for h in recall_hits if contents.get(h.chunk_id)]
        # 2. RRF 基线序（与 reranker 降级口径同一函数、同一入参集）
        rrf_order = degrade_to_rrf_order(content_present, self.top_n)
        # 3. rerank 序（显式传 contents，避免二次查库 + 保证同集）
        resp = await self.reranker.rerank(RerankRequest(
            query=sample.query, user_id=sample.user_id,
            hits=recall_hits, top_n=self.top_n, contents=contents,
        ))
        return StageOutput(
            layer=Layer.RERANK, query=sample.query,
            ranked=_to_ranked(resp.hits),                    # rerank 序（主）
            comparisons={
                "rerank": _to_ranked(resp.hits),
                "degrade_to_rrf_order": _to_ranked(rrf_order),
            },
            rerank_applied=resp.rerank_applied,
            elapsed_ms=resp.elapsed_ms, raw=resp,
        )
```

要点：

- **候选集一致性**：`rrf_order` 与 reranker 内部都基于"对同一 `contents` 过滤出的 content-present 集"。reranker 用 `contents.get(chunk_id)` 过滤、适配器同法过滤，集合与长度一致——这是两序可比的前提（`degrade_to_rrf_order` 的注释亦强调"入参须为已过滤正文的候选"）。
- **不重复查库**：`contents` 显式传入 `RerankRequest`，reranker 复用、不再自查。
- `_to_ranked` 把 `RerankedHit` 映射为 `RankedHit`：`score` 取 `rerank_score`（为 `None` 的 tail/降级项取一个单调递减的占位序，保名次稳定），`rank` 用 `rerank_rank`；`sources` 沿用上游融合来源集合（供需要时归因）。

### 4.3 装配：core-only，直接构造

`PostRecallReranker()` 默认构造即可（无本地模型加载），**不引入 `evaluation → application` 依赖**。如需与生产单例一致，可选复用 `application.recall_pipeline_provider.get_reranker()`，但首版直构更干净；二者行为等价（reranker 无重型初始化）。`top_n` 取 `settings.RERANK_DEFAULT_TOP_N`（=8），记入快照 `rerank_top_n`。

---

## 五、重排指标（⑰ `metrics/rerank.py`）

### 5.1 复用检索层的纯函数

NDCG@k、MRR 的二值相关性定义与阶段 1 完全一致，直接复用 `metrics/retrieval.py` 的纯函数，分别作用于两序：

- 对 `StageOutput.ranked`（= rerank 序）算 `NDCG@k_rerank` / `MRR_rerank`。
- 对 `comparisons["degrade_to_rrf_order"]` 算 `NDCG@k_rrf` / `MRR_rrf`。

### 5.2 核心：对 RRF 的增量 Δ

```
ΔNDCG@k = NDCG@k_rerank − NDCG@k_rrf
ΔMRR    = MRR_rerank   − MRR_rrf
```

口径（technical_design §一/§六）：**rerank 层主看 NDCG@k 与 MRR 的增量**——量化"精排相对纯 RRF 顺序是否把对的排得更前"。Δ>0 才说明 rerank 真正起效；Δ≈0 或 <0 说明这批数据上 rerank 无益甚至有害。指标同时产出绝对值（`*_rerank` / `*_rrf`）与 Δ，便于定位是"基线本就高"还是"rerank 拉升"。

### 5.3 `rerank_applied` 率与诚实归因

- **必报**：本轮 `rerank_applied=True` 的样本比例。降级样本的两序相同、Δ 恒为 0——若不报告占比，大量降级会把整体 Δ 稀释成"无增益"的假象。
- **分组聚合**：整体 Δ 之外，额外给"仅 `rerank_applied=True` 子集"的 Δ（标注该子集 n）——前者答"rerank 在生产降级现实下的净效果"，后者答"rerank 真正执行时的效果"。两者都报，不可只取其一。
- **小样本门槛（B12）**：applied 子集在 50–100 条上可能只剩个位数到二十几条,其 Δ 同样受统计审慎约束——套用 trend §5.2 的**最小样本量门槛(n<30 不判回归、仅定性)+ 噪声地板**,不在小样本上下"显著增益/退化"的强结论。
- 降级原因（模型失败 / 索引不可用）来自日志，非结构化指标；如需归因可在 `detail` 记 `rerank_applied` 标志，报告侧统计。

### 5.4 k 与 top_n 对齐

NDCG@k / MRR 的 k 须 ≤ `top_n`（重排只输出 top_n 个）。报告标注 `top_n` 口径；k 默认仍取 `[1,3,5,10]` 中 ≤ top_n 的值。

---

## 六、运行前置（重排专属）

- **冻结租户须配置 RERANK 模型**：reranker 解析用户 RERANK 模型且 `allow_system_fallback=False`，未配置直接抛异常。冻结评测租户（R2）必须预置可用的 RERANK 模型配置，否则本层无法跑。
- **模型错配**：RERANK 模型与生成层判官、被测 CHAT、生成器模型的错配纪律仍适用（防自评偏置）；快照记录 RERANK 模型名。
- 活栈：需 MySQL（取正文）+ 可用 RERANK provider；属 integration 级，手动/定时跑。

---

## 七、报告增量

复用阶段 1 reporter，rerank 层新增：

- 两序绝对值 + Δ 表（逐 k、逐 type 桶，标 n）。
- `rerank_applied` 率（整体与分桶）。
- 回归判据扩展：`ΔNDCG@k` 由正转负、或 `NDCG@k_rerank` 跌幅 > 0.02 判回归（沿用阶段 1 判据风格，入配置可调）。
- 基线对比按 config（含 RERANK 模型、`top_n`）同口径分组。

---

## 八、完成判据（Definition of Done）

1. `rerank_adapter` 在同一 run 内产出 rerank 序与 `degrade_to_rrf_order` 序，二者基于同一 content-present 候选集（集合与长度一致）。
2. `metrics/rerank.py` 复用检索层纯函数，产出 `*_rerank` / `*_rrf` 绝对值 + `ΔNDCG@k` / `ΔMRR`。
3. 报告含 `rerank_applied` 率，并区分"整体 Δ"与"仅 applied 子集 Δ（标 n）"。
4. 适配器 core-only（直构 `PostRecallReranker`），不新增 `evaluation → api` 依赖。
5. 冻结租户 RERANK 模型就绪，降级路径（模型失败/索引不可用）能被正确识别为 `rerank_applied=False`。
6. 指标对 raw 零依赖；适配器读 `upstream.raw` 取 `RecallHit` 属合法用法。

---

## 九、本阶段不做（划清边界）

- 不做生成/正确性层（judge/RAGAS/非流式生成入口）——阶段 3。
- 不引入分级相关性（仍二值 NDCG）；分级 NDCG 待 schema 增 `relevance_grades` 后再说。
- 不把整轮 run 挂 PR 门禁（依赖活栈 + RERANK 模型）。
- 不改动 reranker 生产代码；评测只读其行为。
