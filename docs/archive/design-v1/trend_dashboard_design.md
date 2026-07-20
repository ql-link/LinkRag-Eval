# 趋势 / 回归看板 — 设计文档

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase1_design.md](phase1_design.md)（检索层，台账上游）、[technical_design.md](technical_design.md)（指标口径与回归判据）
> 范围：在评估框架已有"单轮产出"之上，叠加**多轮趋势与回归看板**——把每轮指标沉淀为可跨轮查询的时序数据，并以可视化呈现涨跌与回归告警。
> 定位：单轮评测的**纯下游消费**，后加不返工；归总架构 M4 收口 / 趋势旁路，不阻塞阶段 1。

---

## 一、结论先行

看板的难点不在画图，在**把指标变成可跨轮查询的时序数据**，并保证"同口径才比"。三条决策：

1. **台账 = 跨轮指标长表。** 把每轮结果拍平成"长表/tidy"行,专供跨轮查询。
2. **台账首选 `eval_metric_result` 表（见 [eval_storage_design.md](eval_storage_design.md)）。** 已采纳独立 eval schema 方案——指标长表就是 `eval_metric_result`，趋势/回归**直接 SQL 查询**，无需单独台账文件。本表在 `src/evaluation/store`（独立 EvalBase、不在 `src/models`），**不触发** CLAUDE.md §四。**无 DB 环境**才回退 DuckDB/Parquet（下文 `ledger.py` 即该回退实现，从各轮 `result.json` 可重建）。
3. **同口径分组比较。** 趋势线按 config 维度（provider 三态 / top_k / enabled_sources）分组，配置变更在时间轴标注成事件；回归判定只在**同 config** 的相邻轮或对基线之间做。**跨 provider 时"噪声恒定"假设减弱，须先做噪声地板校验（见 §五.0）。**

看板先走**自建静态 HTML（trend.html）**，需要交互式钻取时再评估 MLflow；两者吃同一份台账，不冲突。

---

## 二、为什么要台账（而非直接读 result.json）

- 趋势 = 跨轮扫描，逐个读 N 份 `result.json` 既慢又难做分组聚合与回归对比。
- 台账把所有轮的指标摊平到一张长表，一次查询即可出"某指标随轮次、按 config 分组"的序列。
- 台账与单轮产物职责分明：`result.json` 保真（每轮完整快照），台账保查（denormalized 分析视图）。台账损坏/改 schema → 从 `result.json` 重放即可。

---

## 三、台账 schema（与阶段 1 `result.json` 字段对齐）

**长表（tidy）**，每行 = 一轮里一个指标在一个 type 桶上的一个取值：

| 列 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- |
| `run_id` | str | RunContext | `<yyyymmdd-hhmm>-<gitsha>-<标签>`，台账主键的一部分 |
| `ts` | datetime | run_id 解析 | 排序时间轴用 |
| `git_sha` | str | Snapshot | 关联代码版本 |
| `dataset` | str | EvalRequest | 黄金集名（按它分库/分区） |
| `layer` | str | MetricResult.layer | retrieval / rerank / generation / correctness |
| `metric` | str | MetricResult.name | recall / ndcg / mrr ... |
| `k` | int·null | MetricResult.k | 非 k 指标为 null |
| `relevance_scale` | str | MetricResult | `binary`(自有/DuReader) / `graded`(T2Ranking 4级)。**进联合主键**；不同 scale 的 NDCG 不可比、绝不连线 |
| `type_bucket` | str | MetricResult.by_type 键 | `__all__` 表示全集；其余为 QuestionType |
| `value` | float | MetricResult.mean / by_type | 该桶均值 |
| `n` | int | MetricResult.n / by_type_n | 该桶样本量（小样本审慎） |
| **config 维度（来自 Snapshot，用于分组）** | | | |
| `sparse_provider` | str | Snapshot | bge_m3 / bge_m3_http / remote_bge_m3（三态） |
| `top_k` | int | Snapshot | = RECALL_RESULT_LIMIT |
| `score_threshold` | float·null | Snapshot | |
| `enabled_sources` | str | Snapshot | 规范化排序后拼串，如 `bm25,dense,sparse` |
| `rrf_k` | int | Snapshot | |
| `rerank_top_n` | int·null | Snapshot | 阶段 2 起 |
| `chat_model` / `judge_model` / `generator_model` | str·null | Snapshot | 阶段 3 起 |

> **联合主键**：`(run_id, layer, metric, k, relevance_scale, type_bucket)`，追加时按此去重保证幂等。
> **NDCG 口径分名**：二值与分级 NDCG 数值不可比，指标名分别用 `ndcg_binary` / `ndcg_graded`（或同名 + `relevance_scale` 区分），看板强制不同 scale 不连线（B4）。
> **对齐约束**：`result.json`（或 `eval_metric_result` 行）须落齐上述每列——这就是 `eval_metric_result` 表结构（见 eval_storage_design §3.4，本表多加 `relevance_scale` 列）。

---

## 四、台账读写

**首选（DB 模式）**：台账即 `eval_metric_result` 表。写入 = 一轮结果按行 insert（联合主键去重幂等）；查询 = 直接 SQL `JOIN eval_run` 按 config 分组取时序。无需独立台账文件。详见 [eval_storage_design.md §3.4](eval_storage_design.md)。

**回退（无 DB 环境）`storage/ledger.py`**：

```python
class MetricsLedger:                       # 仅无 DB 时启用
    def append(self, result: EvalResult, snapshot: Snapshot) -> None: ...  # 幂等 upsert
    def rebuild(self, run_results) -> None: ...                            # 从各轮 result.json 全量重建
    def query(self, *, dataset, layer, metric, k, relevance_scale="binary",
              type_bucket="__all__", group_by=None) -> "DataFrame": ...
```

实现：DuckDB（单文件 + SQL）或 pandas+Parquet，落 MinIO eval bucket（`eval/ledger.duckdb`）。读下载、写回传；单轮串行追加。**DB 模式与文件模式查询接口一致**，trend_report 不感知后端。

---

## 五、同口径比较与回归判定

### 5.0 噪声地板:回归判据的前提(B1,必做)

整套零人工方案押在"噪声在不同配置间恒定"上,但这是**待验证假设而非定论**——换 provider/模型会非均匀地与噪声交互(脏样本的命中依赖召回模型本身),可能造出"不是真提升的提升"。**M1 跑出首轮数据后第一件事就是测噪声地板**:

1. **同配置重跑**:同一 config、同一黄金集跑 N 次(LLM 召回/判官非确定性),量化每指标的轮间波动 → 得"不可解释波动带"。
2. **等价配置互比**:挑两个理应等价(或差异极小)的 config 跑同一黄金集,看差异是否落在波动带内。若系统性偏出,说明该假设在此场景减弱。
3. **产出**:每指标一个经验噪声阈值 `σ_metric`。**回归判据由它推导**,而非拍脑袋的 2pp/0.02。
4. 报告口径脚注须写明:跨 provider 对比时该假设减弱,结论降级为"提示性"。

### 5.1 同口径分组(规避第一大陷阱)

1. **分组**：趋势线按 `(sparse_provider, top_k, enabled_sources, rerank_top_n, relevance_scale)` 等维度分组，不同 config / 不同 relevance_scale 的点**绝不连成一条线**。
2. **事件标注**：config 变更在时间轴画竖线 + 标签（如"切 remote_bge_m3"），让跌幅可归因。

### 5.2 回归判定(只在同 config 内,且有统计门槛 B6)

- 对基线：选定 baseline run-id（每个 config 组各留各的基线），同口径逐指标 diff;对相邻轮与上一轮**同 config** 比。
- **最小样本量门槛**:某桶 `n < 30` 时**不触发回归**,只标"样本不足、仅定性"。50–100 条分桶后每桶 n≈12–25,Recall@k 单样本翻转就是约 5pp,裸阈值在小样本上几乎必然被噪声触发假回归。
- **判据 = 超噪声地板**:跌幅须**同时**超过 (a) §5.0 的经验阈值 `σ_metric`、(b) 用 bootstrap 重采样/配对检验得出的该桶置信区间,才判回归。`Recall@k 跌>2pp / NDCG 跌>0.02 / Faithfulness 跌>0.05` 仅作**初始占位**,M1 校准后用 `σ_metric` 替换。
- 重排 `applied 子集 Δ`(phase2)同样套用最小样本门槛。
- **不作 PR 自动门禁**（依赖活栈），用于人工/定时回归决策。
- "宁紧勿松"重新表述为:**先校准噪声地板再设判据**——否则"紧"只制造假阳性、消磨对看板的信任。

---

## 六、看板本体

### 路线 A · 自建静态 HTML 趋势报告（推荐先做）

`reporters/trend_report.py`：读台账 → 生成**自包含 `trend.html`**（Chart.js，单文件，可 CDN 引 Chart.js）。内容：

- 每指标随轮次的折线，**按 config 分组多线** + 配置变更事件竖线。
- **回归告警表**：当前最新轮对各自基线的同口径涨跌，超判据标红。
- 按 `type` 桶的小多图（small multiples），标注每桶样本量。

每轮跑完重新生成，推 MinIO + 本地可直接打开。零常驻服务，与现有"出报告"流程一致，改动最小。

### 路线 B · 现成实验追踪（买而非造）

把每轮记为一次 MLflow run：params = 快照 config 维度，metrics = 各 MetricResult。白送跑次对比、指标随时间曲线、平行坐标筛选 UI。适合要交互式钻取又不想自建前端。代价：多一个 MLflow tracking 服务/存储。

### 选型建议

先 **A** 起步（贴合本项目自包含、可复现风格，落地快）；轮次多、需交互式钻取时再评估 **B**。两者吃同一份台账，可平滑叠加。

---

## 七、落地位置与边界

```
src/evaluation/
├── storage/
│   └── ledger.py            # 台账读写：append / rebuild / query
└── reporters/
    └── trend_report.py      # 读台账 → trend.html（Chart.js）

产物（MinIO eval bucket 或 .specs）：
eval/ledger.duckdb           # 指标台账（可重建缓存）
eval/trend/trend.html        # 趋势看板
eval/<dataset>/<run-id>/...  # 单轮产物（snapshot/result/report，台账上游）
```

- 台账与 trend.html 属"产物"，落 MinIO eval bucket（或 .specs）；引擎代码在 `src/evaluation/`。
- 依赖：`ledger`/`trend_report` 只依赖 `models` 与存储后端；不碰 `src.core`，不引入 ORM。
- 归 **M4 收口 / 趋势旁路**，不阻塞阶段 1。前置仅一条：阶段 1 的 `result.json` 按 §三 schema 落齐字段。

---

## 八、可选增强（按需，非首版）

- **趋势异常自动播报**：定时跑评测 + 台账新增轮触发回归判定，超阈值推送（邮件/IM）。
- **多维下钻**：trend.html 加 config 维度筛选器（provider/top_k 下拉）。
- **跨层联看**：检索 NDCG 与生成 Faithfulness 同图，验证"检索退化是否传导到生成"。

---

## 九、完成判据（Definition of Done）

1. `ledger.append` 幂等写入，`rebuild` 能从一批 `result.json` 全量重建出一致台账。
2. `ledger.query` 能按 config 分组返回某指标时序。
3. `trend.html` 出按 config 分组的折线 + 配置变更标注 + 回归告警表 + 分桶样本量。
4. 回归判定严格同口径（不同 config 不互比），判据入配置可调。
5. 台账字段与阶段 1 `result.json` 完全对齐，新增轮无需改 schema。
