# Robust Fusion 候选快照字段缺口审计

记录：`ROBUST-FUSION-P4-01-FIELD-GAP-AUDIT-2026-08-28-v1`

日期：2026-08-28

状态：P4-01 完成证据；只审计当前契约与字段责任，不生成候选快照、不读取 Gate A/Blind 内容、不运行任何研究结果。

对应协议：科研协议 `ROBUST-FUSION-RESEARCH-2026-08-28-v19`、工程协议 `ROBUST-FUSION-ENGINEERING-2026-08-28-v9`。

## 1. 结论

当前 LinkRag 已提供正式研究所需的**三路原始候选入口**：`RecallResponse.candidate_hits` 保留融合截断前的候选并集，`route_hits` 保留 Dense、Learned Sparse、BM25 各自的候选顺序与原始分数；`RecallRequest` 也已有 `candidate_contract_version`、`candidate_profile` 和 `required_sources`。这部分足以作为 P4-02 的上游契约，不需要修改生产 LinkRag。

当前 LinkRag-Eval 的通用 `StageOutput`、`Snapshot` 和历史 LTR cache **不能直接充当 Gate A 正式候选快照**：

1. `RecallEvaluable` 只把最终 `resp.hits` 拍平成 fused `RankedHit`，没有持久化 `candidate_hits` 和逐路 `route_hits`，因而丢失分路原始 rank/score 与未进入最终 Top-K 的候选。
2. 历史 LTR cache 虽保存逐路候选，但把 `expected_chunk_ids` 等评价真值与 Query/route 数据放在同一行，缺少 method/evaluation view 的物理隔离。
3. 通用 `Snapshot` 能记录 route top-k、阈值、融合参数、computer fingerprint、Git 与 BM25 sidecar，但没有固定数据 revision/文件摘要、candidate contract、相似度 manifest、Reranker 卡片、family、压力链、人工关系层和 Seal 身份。
4. SQLite `eval_run.snapshot_json` 只适合运行配置与聚合结果台账；六表模型没有候选快照、关系标注、等价组、压力链或逐方法排序表。正式研究应使用不可变文件快照，SQLite 只登记快照 ID/hash 和运行索引，不把它改造成确认性真值源。

因此 P4-02 应新增 Robust Fusion 专用、文件级、双视图快照；不得扩张通用 `StageOutput.raw` 的指标责任，也不得复用历史 Blind/LTR cache 作为确认性快照。

> **概念解释｜双视图隔离**：方法视图只含排序方法在推理时允许看到的信息；评价视图另存 qrel、等价/冲突标签和压力链等真值。两者用不可变 ID 连接，但方法代码没有评价文件的读取权限。

## 2. 已有字段逐层审计

| 现有载体 | 已有字段 | 可直接复用 | 关键缺口 | P4-02 处理 |
| --- | --- | --- | --- | --- |
| LinkRag `RecallRequest` | Query、user/dataset/doc 范围、三路 Top-K/阈值、enabled/required sources、融合权重、candidate contract/profile | 请求参数与候选契约入口 | 没有研究 dataset revision、cohort、family、目标等价组或 Seal 信息；这些也不应进入生产请求 | Eval 侧在请求外层补研究 envelope；不修改生产类 |
| LinkRag `RetrieverHit` | `chunk_id/doc_id/dataset_id/score/source` | 每一路的原始候选最小单位 | 没有显式 rank、内容 hash、模型/请求快照 | Eval 按返回顺序写 1-based route rank，并从冻结 corpus manifest 补内容 hash；route identity 在根 manifest 统一记录 |
| LinkRag `RecallResponse.route_hits` | 三路各自完整列表 | **正式分路证据来源** | 空路与失败路需要区分；服务端在线权重 revision 只暴露 model ID | 同时保存 required source、empty/failed 状态、请求/输出摘要；provider-managed 权重限制写入 manifest |
| LinkRag `RecallResponse.candidate_hits` | 融合截断前候选并集及各路 score map | **固定候选池来源** | 没有 pool hash、query/corpus revision、内容 hash | Eval 生成确定性 `candidate_pool_id` 和有序成员摘要；逐候选与 route 表交叉校验 |
| LinkRag `RecallResponse.hits` | 最终融合 Top-K | Fixed Fusion 运行结果起点 | 不是完整候选总体 | 只作为一个比较器输出；不得据此裁剪公共候选池 |
| Eval `RankedHit/StageOutput` | fused rank/score、命中 routes、失败路和计数 | 通用召回指标与历史报告 | 丢失逐路 rank/score、完整池、candidate contract 和 diagnostics | 保持通用模型不变；P4-02 直接消费/序列化 `RecallResponse` 的正式字段 |
| Eval `Snapshot` | Git、三路开关、Top-K、阈值、融合、fingerprint、BM25 identity、feature version | 运行配置子集 | 缺数据/标注/相似度/Reranker/Seal 身份；`sparse_vector_provider` 仍带历史 BGE 兼容语义 | Robust Fusion root manifest 引用该配置但增加严格 schema；Gate preflight 拒绝 BGE |
| 历史 LTR candidate JSONL | `sample_id/query/dataset_ids/routes/score/rank/failed_sources/expected_*` | 38 维 LTR-v3 适配逻辑和 Dev 工程经验 | 方法输入与 qrel 同行；无内容 hash、family、压力链、快照根和只读 Seal | 不原样复用；拆成 method/evaluation 两份，并从新冻结候选重新生成 |
| `candidate_contents.json` sidecar | `chunk_id→content` | 候选正文 lookup 形式 | 无 dataset revision、source locator、content normalization/hash | 由 pinned corpus manifest 生成带 locator/hash 的不可变内容表 |
| SQLite `eval_run/eval_metric_result` | snapshot JSON 与聚合指标 | 快照/运行索引、审计查询 | 无行级候选和关系真值 | 只登记 `snapshot_id/root_sha256/method_run_id`；正式内容留在只读文件制品 |

## 3. P4-02 必需的最小字段

### 3.1 根 manifest

| 字段组 | 必填字段 | 责任来源 |
| --- | --- | --- |
| 身份 | `snapshot_id`、schema/version、创建时间、cohort、Gate role | Eval 快照生成器 |
| 协议与代码 | 科研/工程/进度记录、双仓 commit/tree/dirty=false、generator 与 metric code hash | contract-lock + Seal |
| 数据 | dataset ID/name、官方 revision、license/governance、corpus/query/qrels 文件 SHA-256、source split、纳入排除 manifest | P3 固定实体与资格制品 |
| 三路 | Dense `text-embedding-v4`、Sparse Ark/`doubao-embedding-vision-251215`、BM25 SQLite FTS5；端点只存 identity hash；请求配置、模型 ID、Top-K/阈值、失败策略、固定 probe/output 摘要 | route contract + `.env.eval` 的脱敏摘要 |
| 比较器 | Fixed Fusion、RRF、两个 Reranker、LTR-v3 的 ID/version/hash；Gate A 不含 D1—D3/A0/M1 | P3-05 + LTR contract |
| 测量 | similarity manifest ID/hash、相似度代码 hash、Dev 标准化/共同支持/分带版本、annotation handbook/result | P2/P5 |
| 统计 | estimand、cluster、权重、bootstrap、multiplicity、随机种子、实际效应门槛和停止规则版本 | P5 预注册 |
| 完整性 | 所有分片 SHA-256、root hash、clean tag/commit、外部时间戳 receipt sidecar 指针、解锁状态 | P5-07/P5-08 |

根 manifest 必须明确 `gate_a_executed=false`、`outcome_fields_present_in_method_view=false` 和 `bge_m3=RETIRED_FORBIDDEN`。在线 provider 不能暴露精确权重 revision 时，必须保存 model ID、请求摘要和候选输出摘要；复算依赖封存输出，而不是假设 API 权重永久不变。

### 3.2 Query 与 family 表

每行至少包括：

- `dataset_id/dataset_revision/cohort/source_split/query_id/query_text_sha256`；
- `query_family_id/document_family_id/version_family_id/counterfactual_template_family_id`；
- `target_equivalence_group_id` 与目标参照成员 ID 列表摘要；
- exposure/eligibility 状态及排除理由；
- Query 的正文 locator；若正文需要盲化，运行期文件与 curator 文件分离。

跨 Dev/GateA/Blind 任一 family 相交时，生成器必须拒绝，不允许只记 warning。

### 3.3 方法视图候选表

每个 `query_id × chunk_id` 一行，至少包括：

- corpus identity：`chunk_id/doc_id/dataset_id/content_sha256/content_locator`；
- pool identity：`candidate_pool_id`、成员顺序、是否进入 `candidate_hits`；
- 每一路独立的 `raw_score/rank/missing`，以及 source count；
- Fixed Fusion/RRF 所需的冻结输入，不预写被测方法结果；
- 允许进入 LTR-v3 的 Query/正文表面字段由运行时从同一正文纯函数计算，不在快照中混入 qrel 派生字段。

严禁出现：`source_qrel/grade/relevance_status/target_relation/adjudicability/conflict_type/origin/evidence_locator/reviewer_id/expected_chunk_ids`，以及任何 Gate 结果。

### 3.4 评价视图与压力链表

评价视图以同一 `query_id/chunk_id` 键连接，至少包括：

- 不可变原始 qrel 与其来源/revision；
- `relevance_status/target_relation/adjudicability`；
- `target_equivalence_group_id`、证据定位、理由、两名标注员、仲裁状态和手册版本；
- `origin=natural|synthetic`、四类单原子冲突类型、false-negative 审计状态；
- 候选对 `candidate_pair_relation` 及其证据。

压力链表以 `pressure_pool_id/replacement_chain_id` 为键，保存 `query_id × target group × relation × dose` 的成员列表、`n=0/5/10/20/50` 嵌套关系、matched 等价/冲突配对和 Clean 基准池。任何剂量不嵌套、Clean/Stress 的相关等价组集合或组级 gain 变化时必须拒绝。

## 4. 物理文件与访问边界

P4-02 的最低目录建议固定为：

```text
snapshot-root/
  root_manifest.json
  method/query.jsonl
  method/candidate.jsonl
  method/route_hit.jsonl
  evaluation/qrel_and_relation.jsonl
  evaluation/candidate_pair_relation.jsonl
  evaluation/pressure_chain.jsonl
  content/chunk_locator_and_hash.jsonl
  checksums.sha256
```

- `method/` 是所有比较器的唯一输入；运行账户不得读取 `evaluation/`。
- `evaluation/` 只由指标器在排序输出完成后读取。
- `gatea/` 在 P5-08 前保持锁定；`blind/` 不属于 Gate A 快照，继续由 Internal v6 Blind 锁保护。
- 内容正文可按授权留在本地分片，root 只需封存 locator/hash；复现发布不自动重分发全文。
- 任何历史 Blind v4/v5 或其 Query 条件化子池均不得复制进该目录。

## 5. 已关闭与未关闭边界

P4-01 至此可以关闭，因为已有字段、缺失字段、责任来源、双视图边界和最小文件形态均已明确。它没有授权 P4-02：

- 还没有实现专用 schema/validator/writer；
- 还没有通过 P3-05 的两个 Reranker 卡片；
- 还没有冻结新的非 BGE 实验相似度编码器与 Dev 参数；
- 还没有完成 Internal v6 人口、30-family 构造率先导和功效分母；
- 还没有双仓 clean contract-lock、远端绿色 CI 或 Gate A Seal。

下一步工程动作是 P4-02：只在 Eval 侧新增最小 schema 与 validator，直接消费当前 LinkRag 的 `candidate_hits/route_hits`，不修改生产 LinkRag，不恢复 `BucketRouter`，不开发 D1—D3/A0/M1。
