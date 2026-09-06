# Internal Stress v6-Dev 三路检索证据 v5 独立核验报告

> 记录：`ROBUST-FUSION-INTERNAL-V6-DEV-ROUTE-EVIDENCE-VERIFICATION-2026-08-29-v2`
> 核验日期：2026-08-29
> 结论：`VERIFIED`，但仅限 Dev 测量与流程校准；`NOT_ELIGIBLE` for Gate A/B

## Material Passport

| 项目 | 内容 |
| --- | --- |
| 核验对象 | `internal-v6-dev-route-evidence-v5-20260829` |
| 输入 release | `ROBUST-FUSION-INTERNAL-V6-DEV-ADJUDICATED-2026-08-29-v1` |
| 输入 release manifest SHA-256 | `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac` |
| plan SHA-256 | `a7b159cc7f8f2d694e816b820971a8d3bce85c2f1fe392dde5c4c0003df7c03a` |
| manifest SHA-256 | `a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d` |
| content root SHA-256 | `1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550` |
| Qdrant collection | `eval_rf_internal_v6_dev_internal_v6_dev_route_evidence_v5_20260829_9` |
| 数据角色 | 全合成 `internal-v6-dev`；只用于构念、检索、测量和成本校准 |
| Gate 状态 | `gate_a_executed=false`、`gate_b_executed=false`、`gate_eligibility=NOT_ELIGIBLE` |

## 1. 结论

v5 已完成一次执行，并通过独立只读核验。计划回执、manifest 回执、逐文件大小与 SHA-256、文件清单和 content root 均可从现存文件重新计算；SQLite 元数据、SQLite FTS5 和真实 Qdrant collection 中的 112 个 Chunk 身份一致。28 条 Query 在 Dense、Learned Sparse、BM25 三路均有非空召回，全部 28 个 gold target 和 112 条已标注候选均进入候选并集。

本结果证明的是：当前 Dev release 可以被真实三路检索管线物化为有来源分数与排名的双视图研究材料。它不证明高相似事实冲突会导致 Reranker 退化，不估计自然候选构造率，也不解锁 Gate A、Gate B、正式 P4-02 快照或 M1 开发。

## 2. 执行谱系与不可覆盖处理

| 版本 | 状态 | 处理 |
| --- | --- | --- |
| v1 | `SUPERSEDED_BEFORE_EXECUTION` | 执行器收紧后在零尝试状态废止；不改写、不执行 |
| v2 | `FAILED_NO_AUTORETRY` | 首次 Qdrant 只读探测因缺少本地 SSH 转发而超时；0 次 Dense/Sparse 请求，目标 collection 不存在 |
| v3 | `FAILED_NO_AUTORETRY` | 健康隧道下进入执行，但因本地 `storage/` 父目录未预建而在 SQLite 打开时失败；未发出编码 API 请求，目标 collection 不存在 |
| v4 | 执行完成但制品拒收 | 112 个点与 3,056 行候选均已产生；manifest 错误纳入运行期 SQLite `-wal/-shm` 文件，进程结束后无法重算原 content root。原制品保持不变，不作事后重签 |
| v5 | `COMPLETED` / `VERIFIED` | 修复目录预建、SQLite checkpoint、临时 sidecar 排除及 completed state 的 content-root 记录后，以新 run ID 独立执行并验收 |

上述版本均保留各自计划和状态；没有重跑失败计划、覆盖旧目录、删除失败证据或把 v4 重新签名为合格制品。

## 3. 独立验收结果

### 3.1 完整性与隔离

- `run_state.json` 为 `COMPLETED`，`execution_attempts=1`；其中 plan、manifest 和 content-root 摘要均与重新计算值一致。
- manifest 的 12 个受管文件与现存非临时文件逐项一致；不存在 `-wal`、`-shm` 或 `-journal` 条目。
- `method_view/` 只包含 Query/Chunk 正文、生产可见标识与三路分数/排名；递归字段检查未发现人工关系、冲突类型、可裁决性、family 或配额字段。
- `evaluation_view/` 的 112 条关系全部能在候选并集中按 `(query_uid, chunk_id)` 唯一定位。
- `runtime/config_snapshot.json` 只保存模型/端点摘要、参数与 `api_key_present` 布尔值，明确记录 `secrets_persisted=false`；未保存密钥。

### 3.2 数量闭合

| 检查项 | 结果 |
| --- | ---: |
| Query | 28 |
| 文档 Chunk / 已索引 Chunk | 112 / 112 |
| 候选并集长表 | 3,056 |
| 已标注关系 / 已标注候选入并集 | 112 / 112 |
| gold target / gold target 入并集 | 28 / 28 |
| 含失败来源的 Query | 0 |
| Dense 非空召回 Query | 28 |
| Learned Sparse 非空召回 Query | 28 |
| BM25 非空召回 Query | 28 |

关系分布为 `equivalent=56`、`factual_conflict=28`、`other_incorrect=28`。每条 Query 恰有一个 `relevant_gold`；这些是既有双审与主持人裁定的 evaluation view，不是由检索结果反推的标签。

### 3.3 存储与真实中间件

- metadata SQLite 含 112 条 `eval_corpus_chunk`，三项 indexed flag 均为真，Chunk ID 集合与方法视图完全一致。
- BM25 SQLite FTS5 含 112 条索引记录。
- Qdrant collection 状态为 green，含 112 个点；点 ID 与 112 个 Chunk ID 完全一致。
- 每个 Qdrant 点均含 `dense` 与 `sparse_text` 两个 named vector；Dense 维度为 1024，Sparse indices/values 非空且等长。
- 当前客户端 1.19 与服务器 1.17 存在版本提示，但真实 collection 配置、写入、三路检索和独立 REST 核验均通过；该提示作为环境治理事项保留，不改写为数据失败。

## 4. v4—v5 可复现性边界

v4 与 v5 使用相同输入 release 和同一冻结 route profile。独立比较得到：

- Query、Chunk、family 与 `run_summary` 文件逐字节一致；
- 28 个 Query 的候选集合全部一致，3,056 个 `(query_uid, chunk_id)` 键完全一致；
- Top-1 身份和 Top-10 集合对全部 Query 一致；
- 112 条人工语义标签完全一致，所有已标注候选的 candidate rank 均未变化；
- BM25 的 retrieved/rank/score 完全一致，Sparse 只有 1 个 raw score 出现 `6×10⁻⁸` 级差异且排名不变；
- Dense 有 62 个 raw score 数值变化，最大绝对差约 `2.46×10⁻⁴`，2 个 Dense route rank 变化；归一化融合后 259 个 fused score 变化，最大绝对差约 `2.81×10⁻⁴`；
- 8/3,056 个未标注低位候选发生相邻名次交换，最大变化 1 位。

因此本轮达到“候选身份、核心排名集合与标签关系可复现”，但不声称 provider-managed 在线向量及全部浮点分数跨运行逐字节相同。科研协议 v26/工程协议 v17 已在 Gate A 前明确撤销在线 Dense/Sparse 的数值误差与 exact 重放门槛：后续正式快照只生成一次，经结构校验后立即保存逐值证据并哈希封存；数值差异仅作描述，不得据此重跑或在多个运行中择优。该治理修订不改变 v5 的 `VERIFIED/NOT_ELIGIBLE` 结论，也不要求重跑 v5；本地确定性环节仍须精确复现。

## 5. 软件验证

修复后新增真实 SQLite/FTS5 加伪远端端到端回归，覆盖父目录预建、首次执行空存储、双视图、manifest 文件清单、临时 SQLite sidecar 排除和 completed state 的 content root。最终非集成测试结果为：

```text
375 passed, 3 deselected, 7 warnings
```

警告来自既有依赖弃用或版本提示，不改变本报告的通过项。

本报告升级为 v2 后，在线路由结构契约新增 Dense 维度/有限值/非零范数与 Sparse 非空/index-value/top-k/有限值/非零权重测试；现行无数值 Gate 的准入审计 dry-run 同时确认历史 v2 模型/schema 证据与当前策略均为 PASS。更新后的非集成套件结果为 `384 passed, 3 deselected, 7 warnings`；未调用在线 API，也未生成新的候选快照。

## 6. 后续允许与禁止事项

允许：把 v5 用作 v6-Dev 的三路可召回率、相似度测量、候选字段、成本和测量工具校准输入。

现行在线路由策略：`ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2`。本报告中的 v4/v5 数值对比是描述性证据，不是通过线，也不构成挑选运行的依据。

禁止：把 v5 写成 Gate A/B 证据、正式 P4-02 候选快照、自然来源样本、未曝光 Blind，或据此开发和宣称 M1 有效。GateA/Blind 仍须建立独立自然来源锚点、非零自然候选配额、family 零重合、clean/CI/contract-lock 与正式 seal。
