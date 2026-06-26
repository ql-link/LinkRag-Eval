# 阶段 1 · 检索层 — 设计文档

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase0_design.md](phase0_design.md)（地基层）、[technical_design.md](technical_design.md)（五层评估点口径）
> 范围：评估框架第一个**自成闭环、可交付的可跑版本**——只评检索/召回层，跑通"黄金集 → 召回 → 指标 → 报告"全链路。
> 目标：换 provider / 调 top_k·threshold / 改 enabled_sources 后，能产出可信、可复现、可对基线的召回质量数字。

---

## 一、结论先行

阶段 1 交付一条端到端可跑的检索评测链路，由 8 个模块单元构成（对应总架构实现顺序 4–11）。两条设计主线：

1. **指标计算与召回执行彻底分离。** `metrics/retrieval.py` 是**纯函数**（输入黄金集 + `StageOutput`，输出 `MetricValue`），零外部依赖、可单测、进 PR 门禁；召回执行在 `adapters/recall_adapter.py`，需活栈、只手动/定时跑。这条线是阶段 1 能"指标进 CI、整轮 run 离线"的根本。
2. **召回口径严格对齐生产。** 适配器**复用生产的 pipeline 装配单例** `recall_pipeline_provider.get_recall_pipeline()`，而非自己拼三路，保证评测走的就是线上那条融合链路（top_k、RRF、enabled_sources、provider 三态全一致）。

依赖方向：本阶段所有模块只依赖 `contracts`/`models`（阶段 0）与 `src.core`；唯一例外是 `recall_adapter` 复用 `src/application/recall_pipeline_provider`，属有意识的取舍，见 §五.3。

---

## 二、模块清单与产出

```
src/evaluation/
├── golden/
│   ├── schema.py            # ④ GoldenSample dataclass（满足 contracts.Sample）
│   └── loader.py            #    jsonl 加载 + 前置自检（chunk 在库且 ACTIVE）
├── metrics/
│   ├── registry.py          # ⑤ 指标注册/按 layer 取用
│   └── retrieval.py         #    recall@k/precision@k/mrr/ndcg@k/map/三路重叠率/延迟（纯函数）
├── snapshot.py              # ⑥ 抓配置快照 + 三模型错配校验
├── storage/
│   └── filesystem.py        # ⑦ ResultStore 落地 .specs（实现 contracts.ResultStore）
├── adapters/
│   └── recall_adapter.py    # ⑧ 复用 get_recall_pipeline()，RecallResponse → StageOutput
├── runners/
│   ├── context.py           # ⑨ 一次 run 的上下文（run-id/快照/store/资源句柄）
│   └── stage_runner.py      #    单环节驱动：dataset × evaluable × metrics → EvalResult
└── reporters/
    ├── base.py              # ⑩ Reporter 抽象
    ├── html_reporter.py     #    HTML 报告(用 templates/eval_report_template.html)→ reports/<run-id>.html
    └── json_reporter.py     #    机器可读结果

scripts/eval/run.py          # ⑪ 薄 CLI：解析参数 → 调 runner，无业务逻辑
tests/unit/evaluation/
├── test_retrieval_metrics.py   # 指标数学单测（核心，进 PR 门禁）
├── test_golden_loader.py
└── test_report_diff.py
```

---

## 三、黄金集（④ `golden/`）

### 3.1 `schema.py` — `GoldenSample`

落地 phase0 的 `contracts.Sample` 协议，对应 technical_design §三 的 jsonl schema：

```python
@dataclass(frozen=True)
class GoldenSample:
    id: str
    query: str
    user_id: int
    dataset_ids: list[int]
    expected_chunk_ids: list[str]          # 第1层 reference（命中/不命中二值）
    expected_doc_ids: list[int] | None = None   # chunk 失效时的 doc 粒度降级
    golden_answer: str | None = None       # 第1层不需要，留给 2/3 层
    type: QuestionType = QuestionType.KEYWORD
    note: str = ""
```

第 1 层只依赖 `expected_chunk_ids`（与 `dataset_ids`/`user_id`），缺 `golden_answer` 也能独立跑。

### 3.2 `loader.py` — 加载 + 前置自检

```python
def load_golden(path: str) -> list[GoldenSample]: ...       # 读 jsonl、逐行校验必填字段
async def precheck(samples, repo: ChunkRepository) -> PrecheckReport: ...
```

`precheck` 是**可复现的守门**（technical_design §七.2）：校验每条 `expected_chunk_ids` 对应 chunk 在库且 `lifecycle_status=ACTIVE`，否则本轮判无效并报出失效条目（数据可复现 > 指标好看）。失效时回退用 `expected_doc_ids` 给出降级提示。`PrecheckReport` 含失效条目清单，runner 据此决定是否中止。

---

## 四、检索指标（⑤ `metrics/`）

### 4.1 `retrieval.py` — 纯函数指标

输入：`GoldenSample`（提供 `expected_chunk_ids` 作 ground truth）+ `StageOutput.ranked`（按 `fused_score` 降序的 `RankedHit` 列表）。输出：`list[MetricValue]`。全部确定性、无 IO。

设 `R = set(expected_chunk_ids)`（相关集），`ranked = [c_1..c_n]`（按名次），`rel(c)=1 if c∈R else 0`。

| 指标 | 定义 | 排序敏感 | 备注 |
| --- | --- | --- | --- |
| **Recall@k** | `|{c_1..c_k} ∩ R| / |R|` | 否 | 召回层主指标（广召回是否漏） |
| **Hit@k** | `1 if {c_1..c_k} ∩ R ≠ ∅ else 0` | 否 | 至少命中一个 |
| **Precision@k** | `|{c_1..c_k} ∩ R| / k` | 否 | 噪声比 |
| **MRR** | `1 / rank_of_first_relevant`（无命中=0） | 是 | 首位质量 |
| **NDCG@k** | `DCG@k / IDCG@k`，`DCG@k = Σ rel(c_i)/log2(i+1)`（i 从 1） | 是 | **二值相关性**（见下） |
| **MAP** | 单 query 的 AP `= (Σ_{i: rel(c_i)=1} Precision@i) / min(|R|, n)`；多 query 取均值由聚合层做 | 是 | 综合排序质量。除以 `min(|R|, n)` 而非命中数，避免 `|R|>n` 时虚高 |
| **三路重叠率** | dense/sparse/bm25 各自独有/共有命中数 | — | 读 `RankedHit.sources`（归一化集合，不依赖 `raw`），见 §五.2 |
| **各路延迟** | 取自 `StageOutput.elapsed_ms` 等诊断字段 | — | 进报告不进数学指标 |

> **NDCG 口径**：黄金集只有二值命中（`expected_chunk_ids`），故为**二值相关性 NDCG**——反映"对的有没有排前"，不区分高度/弱相关。报告须显式标注此口径。后续若加 `relevance_grades(0/1/2/3)` 再升级为分级 NDCG（technical_design §第1层注）。

k 取值由配置给（默认 `[1,3,5,10]`），一个指标函数一次产多个 `MetricValue`（每个带 `k`）。

口径约定（technical_design §第1层）：**召回层主看 Recall@k**，**rerank 层主看 NDCG@k 与 MRR**（阶段 2 用）。

### 4.2 `registry.py` — 注册与取用

```python
def register(metric: Metric) -> None: ...
def metrics_for(layer: Layer) -> list[Metric]: ...
```

按 `Layer.RETRIEVAL` 取本层全部指标，供 runner 遍历。注册表让阶段 2/3 加指标无需改 runner。

---

## 五、召回适配器（⑧ `adapters/recall_adapter.py`）

### 5.1 职责与 `Evaluable` 实现

实现 phase0 的 `Evaluable` 协议（`layer = Layer.RETRIEVAL`）：

```python
class RecallEvaluable:
    layer = Layer.RETRIEVAL
    def __init__(self, pipeline: RecallPipeline, top_k: int): ...
    async def run(self, sample: Sample, *, upstream=None) -> StageOutput:
        resp = await self.pipeline.execute(RecallRequest(
            query=sample.query, user_id=sample.user_id,
            dataset_ids=sample.dataset_ids, top_k=self.top_k,   # = RECALL_RESULT_LIMIT
        ))
        return self._to_stage_output(resp)
```

`_to_stage_output` 把 `RecallResponse` 映射为 `StageOutput`：`hits`→`ranked`（保 `fused_score` 降序、填 `rank`）、`per_source_counts`/`failed_sources`/`elapsed_ms`→诊断字段、`resp`→`raw`。

### 5.2 三路重叠率：从 `RecallHit.scores` 推导（无需额外调分路）

`RecallHit.scores` 是 `dict[str, float|None]`——某路命中该 chunk 则该路键非 `None`。据此可直接算 dense/sparse/bm25 的独有/共有命中，**不必再单独调 facade/Bm25Retriever**，既省一遍调用又保证与融合输入完全一致。

适配器映射时把每个 hit"非 None 的路集合"填入 `RankedHit.sources`（phase0 §3.2 已将 `sources` 定为 `frozenset[str]`）。重叠率指标**只读归一化的 `ranked[*].sources`，不依赖 `raw`**——与 phase0"指标只认 `ranked`"的解耦原则一致。同理，按路 recall（如 dense 单路是否命中期望）也由 `sources` 推导，无需单独跑分路。

### 5.3 装配复用：对齐生产口径的关键取舍

生产的三路装配权威在 `src/application/recall_pipeline_provider.py`：`get_recall_pipeline()` 按 `RECALL_ENABLED_SOURCES` 装 dense/sparse/bm25（dense 走用户 EMBEDDING 解析、sparse 含本地 BGE-M3、bm25 走 `Bm25Retriever`），并以 `RecallPipelineConfig(strict=...)` 构造单例。

适配器**直接复用 `get_recall_pipeline()`**，不自己拼三路。理由：technical_design §六/§九 的第一原则是"评测口径必须与生产一致"，自己拼极易与线上漂移（top_k、RRF、provider 三态、score_threshold）。

> **取舍说明（需在文档与 CI 注释里写明）**：该 provider 物理位于 `src/application/`，复用它使 `recall_adapter` 产生 `evaluation → application` 依赖，偏离"evaluation 仅依赖 core"的理想。两种处置：
> - 首版（推荐）：直接复用 provider，换取口径绝对一致；在 import-lint 白名单里显式放行 `recall_adapter → application.recall_pipeline_provider` 这一条。
> - 后续收口：把装配逻辑下沉到 `core`（如 `core/pipeline/recall/assembly.py`），application provider 与 eval adapter 共用，彻底回归 `evaluation → core`。建议在 M4 收口时做。

### 5.4 provider 三态覆盖

`SPARSE_VECTOR_PROVIDER` 的 `bge_m3 / bge_m3_http / remote_bge_m3` 三态影响召回结果，尤以 `remote_bge_m3`（dense+sparse 同出）影响面最大。适配器不感知三态切换（由 settings 决定），但**快照必须记录当前态**（见 §六），对比时按三态分别留基线。

### 5.5 跨配置多轮的执行约束（`lru_cache` 陷阱，必读）

`get_recall_pipeline()` 是 `@lru_cache(maxsize=1)` **进程内单例**，且各路配置（`RECALL_ENABLED_SOURCES`、`SPARSE_VECTOR_PROVIDER`、`score_threshold` 等）在装配期从 `settings` 读定。这与本模块头号用例"**换 provider / 调 enabled_sources 做回归对比**"直接冲突：

- 同进程内改 `settings` **不会**重建 pipeline（缓存命中旧实例），本地 BGE-M3 也只在首次加载。
- 因此跨配置对比**不能在同一进程里改 settings 连跑多态**。

约束（二选一，首版取前者）：

1. **每个配置态起独立进程**：一态一次 `scripts/eval/run.py`，配置经环境变量/`.env` 注入，进程级隔离，最稳、与生产装配完全一致。
2. **提供绕过缓存的直建入口**：评测侧调 `_build_pipeline()`（非 `lru_cache` 包装版）按需用指定配置重建，代价是本地 BGE-M3 每态重载、且需确保与 provider 同源。仅在单进程内确需连跑多态时使用。

CLI/运行文档须显式写明此约束，避免"看似切了 provider、其实跑的还是旧单例"的假结果。

---

## 六、配置快照（⑥ `snapshot.py`）

落地 phase0 `Snapshot`，从 `settings` 抓检索层口径：`SPARSE_VECTOR_PROVIDER`（三态）、`top_k=RECALL_RESULT_LIMIT`、`score_threshold`、`RECALL_ENABLED_SOURCES`、`rrf_k`、git sha。第 1 层用不到生成层字段（chat/judge/generator 模型），留空或标 `N/A`；`validate_model_distinctness` 在有生成层时才有意义，本阶段仅占位。

```python
def capture(run_id: str, settings) -> Snapshot: ...   # 落 .specs/snapshots/<run-id>.yaml
```

快照保证"用什么口径跑出来的"可追溯——换 provider/调参后能定位数字差异来源。

---

## 七、运行器（⑨ `runners/`）

### 7.1 `context.py` — run 上下文

```python
@dataclass
class RunContext:
    run_id: str          # <yyyymmdd-hhmm>-<gitsha>-<标签>
    snapshot: Snapshot
    store: ResultStore
    top_k: int
    k_values: list[int]  # [1,3,5,10]
```

### 7.2 `stage_runner.py` — 单环节驱动

```python
async def run_stage(
    dataset: list[GoldenSample], evaluable: Evaluable,
    metrics: list[Metric], ctx: RunContext,
) -> EvalResult:
    # 1. precheck 已在入口完成（失效则不进此处）
    # 2. for sample: output = await evaluable.run(sample)
    #                for m in metrics: values += await m.compute(sample, output)
    #                （compute 统一 async，见 phase0 §4.3；检索层内部纯函数，await 无副作用）
    # 3. 聚合：按 (name,k) 求 mean + 按 sample.type 分桶（MetricResult.by_type/_n）
    # 4. 返回 EvalResult(run_id, snapshot, metrics)
```

聚合时每桶标注样本量（`by_type_n`）——首版 50–100 条分桶后 n 很小，报告对小样本桶只作定性参考（technical_design §七.6）。

---

## 八、报告与产物（⑩ `reporters/` + ⑦ `storage/`）

### 8.1 `storage/`（ResultStore）

实现 `contracts.ResultStore`：结构化结果/快照落库（DB 后端，见 [eval_storage_design.md](eval_storage_design.md)）或文件后端回退；`save_report` 写 **HTML 报告**（对象存储 `reports/<run-id>.html` 或 `.specs/`）；`load_baseline` 读基线 run 的结构化结果。

### 8.2 `reporters/html_reporter.py` — HTML 报告（结果表 + 基线 diff + 回归判据）

人读报告为 **HTML**（非 markdown），用统一模版 [`templates/eval_report_template.html`](templates/eval_report_template.html)（自包含、零外部依赖、离线可开、涨绿跌红一眼可见）。`html_reporter` 把结构化结果注入模版渲染：

- **配置快照条 + verdict**：顶部 chips 展示 provider/top_k/enabled_sources/模型等同口径维度 + PASS/回归 徽标。
- **headline 卡片 + 分层结果表**：逐指标 × 逐 k × 逐 type 桶（标 n），含三路重叠率与各路延迟；表头/脚注标注 top_k 口径与"二值 NDCG"。
- **基线 diff**：同口径逐指标涨跌（Δ 着色）；三态 provider 各留各的基线，不混比。
- **指标含义块**：报告内置「指标含义」对照表，逐条用一句话解释本次出现的指标（Recall/Precision/Hit Rate/NDCG/MRR/MAP/三路重叠），只列本次实际出现者；结果表的指标名加 `<abbr title>` 悬停释义。让不熟检索口径的读者无需外查文档即可读懂数字（口径权威仍在 §4.1，此处为面向读者的白话版）。
- **回归告警 + 判据脚注**：`Recall@k 跌>2pp / NDCG 跌>0.02` 仅为**初始占位**；正式判据须**超噪声地板 `σ_metric` 且满足最小样本量 n≥30**（M1 校准,见 [trend_dashboard_design.md §5.0/§5.2](trend_dashboard_design.md)）。小样本桶只标"样本不足、仅定性",不触发回归。**不作 PR 自动门禁**。

`json_reporter.py`（或 DB 写入）输出机器可读结构化结果，供 baseline 加载与趋势。**字段约束**：须落齐 [trend_dashboard_design.md §三](trend_dashboard_design.md) / [eval_storage_design.md](eval_storage_design.md) 所需全部列（run_id/ts/git_sha/dataset/layer/metric/k/type_bucket/value/n + 各 config 维度），使趋势看板与 HTML 报告纯下游消费、零返工。

---

## 九、CLI 入口（⑪ `scripts/eval/run.py`）

薄壳，逻辑全在引擎：

```
python scripts/eval/run.py --golden <path> --layers retrieval --run-id <id> [--baseline <run-id>]
```

仅：解析参数 → `load_golden` + `precheck`（失败即退）→ `snapshot.capture` → 构 `RunContext` → `get_recall_pipeline()` 建 `RecallEvaluable` → `run_stage` → reporter 出报告。无任何指标/召回逻辑。

---

## 十、运行前置与执行模型

- **活栈**：`recall_adapter` 调真实链路，需活的 MySQL + Qdrant + ES 且已灌冻结评测语料（phase0 §六.4 / R2）。
- **门禁边界**：`metrics/retrieval.py` 数学纯函数 → 单测进 PR 门禁；整轮 run → 手动/定时，不挂 PR。
- **可复现**：黄金集绑冻结语料某次 ingestion；run-id 与 snapshot/report 一一对应。

---

## 十一、完成判据（Definition of Done）

1. `python scripts/eval/run.py --layers retrieval` 在 seed 好的栈上跑通，产出结构化结果（DB/json）与 HTML 报告 `reports/<run-id>.html`。
2. `metrics/retrieval.py` 全部指标有单测（含边界：无命中、R 为空、k>n），进 PR 门禁。
3. 报告含分桶样本量、top_k 与二值 NDCG 口径标注、三态 provider 区分。
4. 基线 diff 与回归判据可跑，判据值在配置中可调。
5. `precheck` 能拦住失效黄金集并报出条目。
6. 召回口径经核对与生产一致（复用 `get_recall_pipeline()`）。

---

## 十二、本阶段不做（划清边界）

- 不做重排（`rerank_adapter`/`metrics.rerank`）——阶段 2。
- 不做生成/正确性（judge/RAGAS/非流式生成入口）——阶段 3。
- 不做黄金集合成器（`golden/gen/`）——阶段 1.5；本阶段用人工/已有的小批黄金集即可起步。
- 不把整轮 run 挂 PR 门禁（依赖活栈）。
