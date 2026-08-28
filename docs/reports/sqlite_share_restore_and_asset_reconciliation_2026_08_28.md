# SQLite 工作副本恢复与检索资产逐数据集对账

> 记录：`SQLITE-SHARE-ASSET-RECONCILIATION-2026-08-28-v4`
> 日期：2026-08-28（Asia/Shanghai）
> 范围：`linkrag-eval-sqlite-share-20260827`、本地工作副本、`.env.eval` 指向的旧 eval MySQL 与远端 Qdrant、`ssh linkcv` 的项目文件存在性核对
> 操作边界：只恢复本地文件并执行只读查询；未调用模型，未运行 Blind，未写入远端数据库，未写入、删除或重建远端 collection，也未在服务器部署项目。

> 本报告中的“对账”是资产盘点：确认各存储中有哪些数据集和 Chunk，并比较 Chunk ID 与元数据交集。历史 collection 的额外记录或当前 sidecar 未覆盖的记录不据此判为数据错误。

## 结论

三份 SQLite 工作副本已恢复到 `.env.eval` 使用的 `runs/` 路径，文件摘要与分享包一致，三个数据库的 `PRAGMA quick_check` 均为 `ok`，配置可正常解析。

- 主 SQLite：22 个数据集目录项，其中 21 个有语料，共 49,774 个 Chunk；51 条历史 run、2,884 条指标记录；query/qrel 均为 0。
- 本地 SQLite FTS5 BM25：31,072 条、11 个数据集。全部 Chunk ID 都存在于主 SQLite，数据集 ID 和文档 ID 不一致数均为 0。
- Alt Embedding：20,772 条、9 个数据集，全部为 1,024 维。全部 Chunk ID 都存在于主 SQLite；数据集 ID、文档 ID、内容摘要不一致数均为 0。
- 当前 `.env.eval` Qdrant：`eval_doubao_v2_kb_bucket_9`，状态 `green`，44,773 点。全部 Chunk ID 都存在于主 SQLite；数据集 ID、文档 ID 不一致数均为 0。
- 当前 Qdrant 未承载的 5,001 个主 SQLite Chunk 是 `990131` 的 5,000 条和 `990998` 的 1 条；它们可在其他历史 `eval` collection 中找到。此处只记录分布，不执行迁移或清理。
- 其他历史向量 collection 的逐数据集并集包含 8,201 个与当前主 SQLite 相交的 Chunk，以及 5,550 个仅见于历史远端的 Chunk。后者按既定口径视为历史/残留资产，不判为异常。
- `.env.eval` 指向的旧评测 MySQL `tolink_rag_eval_db` 仍可只读访问：20 个 dataset、39,474 个 Chunk、51 个 run、2,884 条 aggregate metric，query/qrel 均为 0。其 39,474 个共有 Chunk 与本地主 SQLite 在 dataset/doc/source passage/ordinal/content hash 上逐项一致，51 个 run ID 和 2,884 个指标值也完全一致。
- 本地主 SQLite 比旧 MySQL 多出的 10,300 个 Chunk 只来自 `993103` 的 10,000 条与 `993104` 的 300 条，符合 Blind v5 后续追加资产；不是旧库同步丢失。
- `ssh linkcv` 可免交互登录，但该主机是中间件服务器，从未部署 LinkRag-Eval。已在普通用户可读的项目、备份和数据目录中核对，未发现 LinkRag-Eval、`runs/golden_v2` 或本研究行级 qrels/candidate 资产；因此不再把服务器文件系统当作研究真值恢复源。
- 公开实体交叉审计进一步限定了“可复用”的含义：`990126=dureader_800_v2` 与 `990127=cmedqa_800_v2` 各 800 个 `source_passage_id` 全部存在于对应 pinned C-MTEB corpus，但正文完全一致数都是 0，且 SQLite 内容可见明显乱码。两集只能复用 ID/provenance/索引覆盖，不能复用正文做研究语义计算。

## 分享包在 Robust Fusion 研究中的正式角色

该分享包是“高相似度干扰下多路来源感知鲁棒融合”研究想法的经验与工程起点，不只是恢复用备份：

- 历史三路召回、融合、Reranker、LTR-v3 与 Blind 运行提供了提出问题的经验背景；
- 三份 SQLite、旧 eval MySQL 和远端检索资产的一致性证明这条工程谱系真实存在，可用于可行性、成本和重建范围评估；
- 已验证的 ID/provenance、索引覆盖、模型与运行指纹，以及逐数据集正文复核通过的材料，可作为新候选快照的工程底座。

它的证据边界不是“无科研价值”，而是“有重要的发现性/溯源价值，没有确认性真值资格”。两端 `query/qrel=0`，历史 Blind 已曝光，聚合结果无法恢复逐 Query 候选和关系标签；因此分享包不能直接进入 Gate A/B 分母，也不能把历史增量升级为 C1/C2/C3。该分层已写入科研协议 v17 和 [Internal Stress v6 数据协议](../plans/robust-fusion-internal-stress-v6.md)。

## 恢复记录

原始分享包保持不变，工作副本权限设为 `0600`。分享包目录已加入 `.gitignore`，避免其 README、摘要文件或数据库被误提交。

| 文件 | 工作副本 | SHA-256 | `quick_check` |
| --- | --- | --- | --- |
| `linkrag_eval.sqlite3` | `runs/linkrag_eval.sqlite3` | `2727587457c7f231425f8ff983e76b5b4a6e160c31b8d7c029cbeabb5f6586b8` | `ok` |
| `bm25_eval.sqlite3` | `runs/bm25_eval.sqlite3` | `158404a43f74eb11c586517ad0ccd1e4709b3b75ea0c053684bce808500c7699` | `ok` |
| `alt_embedding_eval.sqlite3` | `runs/alt_embedding_eval.sqlite3` | `578b93a032c5dc45faee5d7bd936d3a227c266c262938d376c094d4820f51d2c` | `ok` |

配置解析结果：`EVAL_DB_URL`、`EVAL_BM25_SQLITE_PATH`、`EVAL_ALT_EMBED_SQLITE_PATH` 均指向上述已存在文件；`EVAL_BM25_MODE=sqlite_fts5`；Python 依赖检查无冲突。主库 Alembic 版本为 `0003`。

## `.env.eval` 远端记录对应关系

本节只记录非密钥身份和只读统计；未打印账号、密码、API key 或完整连接串。

| 远端资产 | 只读实况 | 与分享包/本地工作副本的关系 | 科研可用边界 |
| --- | --- | --- | --- |
| 旧 eval MySQL `tolink_rag_eval_db` | 20 dataset / 39,474 Chunk / 51 run / 2,884 metric / 0 query / 0 qrel | 39,474 个共有 Chunk 内容与关键 provenance 字段一致；run/metric 逐项一致 | 可证明分享包中的旧工程状态真实；不能恢复 Query、qrels、候选池或语义标签 |
| 当前 eval Qdrant | `eval_doubao_v2_kb_bucket_9`，44,773 点 | 全部是本地主 SQLite 子集；dataset/doc ID 无不一致 | 可复用已有 dense/sparse 向量；不是 Query 级三路快照 |
| 本地 SQLite 工作副本 | 22 dataset / 49,774 Chunk / 51 run / 2,884 metric / 0 query / 0 qrel | 包含旧 MySQL 全部 39,474 Chunk，并追加 Blind v5 的 10,300 Chunk | 是后续候选重构的 provenance 底座；正文必须逐数据集验证，`990126/990127` 不可用；仍须另建正式 Query/qrels/关系层 |

从科研角度，这个对应结果排除了两种错误解释：分享包不是无法验证来源的孤立副本；同时，远端运行记录也没有隐藏的确认性 Query/qrels 可以直接进入 Gate A。正确做法是复用已验证的 ID/provenance、索引、向量和运行指纹，对正文做逐集权威对账，再重建并独立封存研究用 Query、qrels、等价组与冲突标签。

## `990126/990127` 正文资格补充审计

本轮将两组历史集分别与新落盘官方固定实体逐 `source_passage_id` 对齐：

- `990126` 对应 `C-MTEB/DuRetrieval@a1a333e290fe30b10f3f56498e3a0d911a693ced`；
- `990127` 对应 `C-MTEB/CmedqaRetrieval@cd540c506dae1cf9e9a59c3e06f42030d54e7301`。

| dataset | SQLite 数 | 官方 ID 命中 | 官方正文完全一致 | 结论 |
| --- | ---: | ---: | ---: | --- |
| `990126` | 800 | 800 | 0 | 仅 ID/provenance 可用 |
| `990127` | 800 | 800 | 0 | 仅 ID/provenance 可用 |

可见内容是中文 UTF-8 字节被错误解码后的常见形态，但当前没有 ingestion revision、原始编码、转换链或逐行输入摘要，无法证明某个逆转脚本能无损恢复全部正文。因此本轮不修改 SQLite，也不将“ID 全部命中”误报为“正文已核验”。后续科研 loader 必须从 pinned 官方文件重建这两组正文；历史 BM25/Alt/Qdrant 中与它们关联的向量或 token 也不得继承到正式快照。

## 逐数据集对账

表中：

- `D/S/B 标记` 是主 SQLite 中 `dense_indexed / sparse_indexed / bm25_indexed` 的记录数，仅表示历史入库状态字段。
- `BM25` 是当前本地 SQLite FTS5 sidecar 的实际记录数。
- `Alt` 是本地 Alt Embedding cache 的实际记录数。
- `当前 Qdrant` 是 `.env.eval` 的 `eval_doubao_v2_kb_bucket_9`。
- `其他 Qdrant` 以“与主 SQLite 相交 / 仅历史远端”表示四个其他向量 collection 的逐数据集 Chunk ID 并集；不把同一 Chunk 在多个 collection 中的副本重复计数。

| 数据集 ID | 名称 | 主 SQLite | D/S/B 标记 | BM25 | Alt | 当前 Qdrant | 其他 Qdrant：相交 / 仅远端 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 990121 | 仅历史远端 | 0 | 0/0/0 | 0 | 0 | 0 | 0 / 499 |
| 990122 | 仅历史远端 | 0 | 0/0/0 | 0 | 0 | 0 | 0 / 250 |
| 990123 | `ecom_800_v2` | 800 | 800/800/800 | 0 | 0 | 800 | 800 / 1,200 |
| 990124 | `video_800_v2` | 800 | 800/800/800 | 0 | 0 | 800 | 800 / 1,200 |
| 990126 | `dureader_800_v2` | 800 | 800/800/800 | 0 | 0 | 800 | 800 / 1,200 |
| 990127 | `cmedqa_800_v2` | 800 | 800/800/800 | 0 | 0 | 800 | 800 / 1,200 |
| 990131 | `tech_synth` | 5,000 | 5,000/5,000/0 | 0 | 0 | 0 | 5,000 / 0 |
| 990901 | `spark_pilot_20260708_001` | 12 | 12/12/12 | 12 | 12 | 12 | 0 / 0 |
| 990997 | `smoke_eval_formal_v2` | 1 | 1/1/0 | 0 | 0 | 1 | 0 / 0 |
| 990998 | `smoke_eval_live_named_dense` | 1 | 1/1/0 | 0 | 0 | 0 | 1 / 0 |
| 990999 | `smoke_eval_live` | 0 | 0/0/0 | 0 | 0 | 0 | 0 / 1 |
| 991001 | `golden_v2_synth_background_991001` | 120 | 120/120/120 | 120 | 120 | 120 | 0 / 0 |
| 991002 | `golden_v2_spark_official_background_991002` | 260 | 260/260/260 | 260 | 260 | 260 | 0 / 0 |
| 991003 | `golden_v2_spark_gap_background_991003` | 160 | 160/160/160 | 160 | 160 | 160 | 0 / 0 |
| 991004 | `golden_v2_spark_gap_background_991004` | 220 | 220/220/220 | 220 | 220 | 220 | 0 / 0 |
| 992000 | `golden_v2_scale_992000` | 5,000 | 5,000/5,000/5,000 | 5,000 | 5,000 | 5,000 | 0 / 0 |
| 992001 | `golden_v2_scale_992001` | 5,000 | 5,000/5,000/5,000 | 5,000 | 5,000 | 5,000 | 0 / 0 |
| 992002 | `golden_v2_scale_992002` | 5,000 | 5,000/5,000/5,000 | 5,000 | 5,000 | 5,000 | 0 / 0 |
| 992003 | `golden_v2_scale_992003` | 5,000 | 5,000/5,000/5,000 | 5,000 | 5,000 | 5,000 | 0 / 0 |
| 993100 | `blind-v4-t2retrieval-20k` | 200 | 200/200/200 | 0 | 0 | 200 | 0 / 0 |
| 993101 | `blind-v4-t2retrieval-v2-10k` | 10,000 | 10,000/10,000/10,000 | 0 | 0 | 10,000 | 0 / 0 |
| 993102 | `blind-v4-structured-v1` | 300 | 300/300/300 | 0 | 0 | 300 | 0 / 0 |
| 993103 | `blind_v5_production_v3` | 10,000 | 10,000/10,000/10,000 | 10,000 | 0 | 10,000 | 0 / 0 |
| 993104 | `blind_v5_structured_v2` | 300 | 300/300/300 | 300 | 0 | 300 | 0 / 0 |

## ID 与元数据一致性

| 资产 | 实际记录 | 唯一 Chunk ID | 与主 SQLite 相交 | 仅该资产 | 数据集 ID 不一致 | 文档 ID 不一致 | 内容摘要不一致 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 本地 SQLite FTS5 BM25 | 31,072 | 31,072 | 31,072 | 0 | 0 | 0 | 不适用 |
| 本地 Alt Embedding | 20,772 | 20,772 | 20,772 | 0 | 0 | 0 | 0 |
| 当前 Qdrant | 44,773 | 44,773 | 44,773 | 0 | 0 | 0 | 不适用 |

Alt Embedding 的 20,772 条记录维度均为 1,024，模型标识均为 `BAAI/bge-m3` 的同一缓存口径。三个资产均无重复 Chunk ID。

## 远端 Qdrant collection 清单

所有 collection 均为只读检查，状态均为 `green`。

| Collection | 定位 | 点数 | 与主 SQLite 相交 | 仅远端 | 向量结构 |
| --- | --- | ---: | ---: | ---: | --- |
| `eval_doubao_v2_kb_bucket_9` | 当前 `.env.eval` | 44,773 | 44,773 | 0 | named dense 1,024 维 + `sparse_text` |
| `eval_doubao_kb_bucket_9` | 历史向量 | 5,001 | 5,000 | 1 | unnamed dense 1,024 维 + `sparse_text` |
| `eval_kb_bucket_9` | 历史向量 | 13,684 | 8,135 | 5,549 | named dense 1,024 维 + `sparse_text` |
| `eval_smoke_kb_bucket_9` | 历史 smoke | 1 | 1 | 0 | named dense 1,024 维 + `sparse_text` |
| `eval_v2_kb_bucket_9` | 历史向量 | 3 | 3 | 0 | unnamed dense 1,024 维 + `sparse_text` |
| `eval_bm25` | 历史 Qdrant BM25 | 3,200 | 3,200 | 0 | `bm25_text` sparse vector |

历史 `eval_bm25` 恰好覆盖 990123、990124、990126、990127，各 800 条；Chunk ID、数据集 ID 和文档 ID 均与主 SQLite 一致。当前配置使用本地 `sqlite_fts5`，因此该 collection 不计入上表的本地 BM25 列。

## 后续使用边界

1. 这次恢复只建立可运行工作副本，没有证明任一历史 run 可直接复现；重新评测仍需冻结候选快照、模型指纹和代码版本。
2. `bm25_indexed` 是历史状态字段，不能替代对当前 `bm25_eval.sqlite3` 的实际计数。例如 Blind v4 的 10,500 条在状态字段中为已索引，但不在本次本地 FTS5 sidecar 内。
3. 当前 Qdrant 与主 SQLite 是严格的 44,773 条子集关系；需要运行某个数据集前，应按实验清单确认该数据集所需路由是否实际存在，不根据历史 flag 推断。
4. 历史/残留 collection 维持原状。本报告不提出删除、合并或重建建议。
5. 旧 MySQL 与 SSH 主机都不再作为行级 golden 恢复路径；以后除非出现新的具体备份线索，不重复扫描服务器目录。
6. 历史 51 个 run 与 2,884 个 aggregate metric 只能证明工程运行存在和分享包对账一致；它们没有逐 Query 数据，且相关 Blind 已曝光，不能转为 Gate A/B 确认性证据。
7. 分享包继续作为研究假设 provenance、工程可行性和预算依据，并进入 Internal v6 的来源资格台账；这种正式地位不授予任何历史数据 Gate 身份。
