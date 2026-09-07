# Gate A 数据覆盖、标签覆盖与研究缺口审计

记录：`ROBUST-FUSION-GATE-A-DATA-AUDIT-2026-08-28-v10`

日期：2026-08-28

状态：P3-01 完成证据，兼作 P2-01 / P3-02 前置审计；**不是** Gate A 数据封存记录，也不构成 Gate A 运行结果。

对应协议：

- 科研协议 `ROBUST-FUSION-RESEARCH-2026-08-28-v19`；
- 工程协议 `ROBUST-FUSION-ENGINEERING-2026-08-28-v9`；
- 推进清单 `ROBUST-FUSION-PROGRESS-2026-08-28-v19`。

## 1. 结论

1. 当前没有任何本地 cohort 可以直接进入 Gate A。主 SQLite 中 `eval_query=0`、`eval_qrel=0`，历史行级 golden、candidate、qrels 与 route snapshot 未随分享包恢复；Blind v4/v5 又已曝光。
2. T2 应从原始 `THUIR/T2Ranking` 冻结，而不是把 `C-MTEB/T2Retrieval` 紧凑正例池当作完整检索语料。原始 T2 有四级人工 qrels，可提供较强的 relevance 起点，但仍不提供本文所需的事实等价、事实冲突和 unknown 标签。
3. `Lo/rerankers-and-lexical-similarities` 的 DRUID `standard` 可作为英文 RQ1/RQ2 现象与构件复现。它有候选级 stance/helpfulness，但 Gold 表示原事实核查来源，不等于正确、相关或等价；其候选也不是本文 Dense、Learned Sparse、BM25 三路召回总体。
4. MedicalRetrieval 已退出本研究的确认性主分母。C-MTEB 的 100,999-passage 派生规则虽已通过逐 ID/正文对账恢复，但它只是原始 corpus 的前 99,999 个 PID 加全部 Dev 正例，负例分布不代表完整语料；更关键的是官方 Multi-CPR 仓库和 C-MTEB card 均未明确数据许可证。
5. 公开标签和本地资产可以把人工工作压缩到高相似候选、等价证据、疑似事实冲突与疑似漏标项，但不能消除人工确认。按科研协议固定的 `n=20` 等价链与冲突链计算，确认性标注的理论下界是每个有效 Query 至少 40 个压力候选的内容核验。
6. P2-01 的统计 estimand 已基本封闭；研究负责人已同意把单一四值关系标签拆为“来源相关性”“目标事实关系”和“方法可裁决性”三个正交字段，候选对标签另存。该变更由科研协议 v13 引入并在 v15 保留，标注手册 v1 已同步；未查看 Gate A/B 结果且不改变 Gate estimand。
7. T2 的行级曝光恢复仍保留 1,302 项已知排除制品，但不再依赖猜测丢失的 11 个 ID。存活脚本、manifest 和逐行对账均表明历史 v4/v5 来自 C-MTEB T2，而 C-MTEB T2 恰好是原始 T2 Dev 正例投影；新落盘的原始 Train 258,042 个 Query 与 Dev 的 Query ID 交集为 0。因此候选的曝光关闭规则是：整个原始 Dev 只作校准/已曝光数据，Gate A 与 Blind 只从原始 Train 按 Query family 再分。这是 split-level 保守关闭，不是对 11 个身份的伪恢复；若 Seal 前新找到的证据显示 Train 也曾曝光，必须扩大排除，Seal 后才发现则该 cohort 失效。
8. MedicalRetrieval 的许可本轮仍未解决：固定 Multi-CPR commit 只有 `data/rerank/retrieval/README.md`，没有 `LICENSE`；C-MTEB card 仍为“More Information needed”。本轮最初同时审计 DuRetrieval 与 cMedQA2/CmedqaRetrieval；上游 cMedQA2 最终承担条件、数字、否定与适用范围较密集的中文主数据角色，医学域只作为预注册分层属性，不产生独立研究终点或 Gate。DuRetrieval 完整、独立保留为辅助稳健性数据，两者不再互为可切换的 Gate 备选。
9. 研究负责人已确认本项目属于非商业科研，并接受“原始全文只在本地研究环境使用、复现制品不重分发全文”的保守治理。上游 `cMedQA2@85feb9278c3ae552c591205cbf3e828368c91f8f` 因而正式替换许可不明的 MedicalRetrieval；C-MTEB Cmedqa 的 100,001 条混合语料仍被排除。
10. DuRetrieval 本身是独立公开检索数据集，不应与 C-MTEB Cmedqa 混称。固定 C-MTEB compact revision 的 100,001 条 corpus、2,000 个 Query 与 9,839 条 qrel 作为一个完整实体保留，重合审计不删除、合并或替换其中任何记录。这里的“完整”限于 pinned compact revision，不等于上游约 800 万 passage 的全量 DuReader corpus。
11. 确定性逐条来源剥离把 Cmedqa compact corpus 分为 `Du-only 88,242 / cMedQA2-only 7,137 / both 2,086 / unresolved 2,536`；原先的 90,328 是 `Du-only + both`，不是 90,328 条都能排他地归给 DuRetrieval。全部 2,536 条 unresolved 保持一个仅审计类别，不按 qrel 关联单列，也不做回配、专项标注、删除或正式语义使用。
12. 分享包现正式记录为研究问题的经验起点和工程底座。Internal Stress v6 的唯一 ID、三分目录、访问锁、摄取 schema 与来源资格台账已经建立；由于现有各端 Query/qrel 仍为 0，v6 人口为空且 `NOT_ELIGIBLE`，不改变“当前没有 cohort 可直接进入 Gate A”的结论。
13. 已生成 `ROBUST-FUSION-GATE-A-ELIGIBILITY-2026-08-28-v1` 的 ID/hash-only 资格上界制品：T2 Train 258,042 个 Query family 与 Dev 零交叉；cMedQA2 在跨 split family 排除后，Gate A/Blind 资格上界分别为 99,894/3,954；DuRetrieval 的 100,001 corpus、2,000 Query、9,839 qrel 全量零删减。该制品只关闭第一层 Query-family/split 泄漏，不是最终分母。
14. 真实三路已纠正并由固定无标签探针核对：Dense 为 `text-embedding-v4`，Learned Sparse 为火山方舟 Ark/`doubao-embedding-vision-251215` 在线 API，BM25 为 SQLite FTS5。BGE-M3 只是历史 Alt Embedding 资产，已退出当前 route、实验相似度与独立审计；任何 Gate A preflight 发现 BGE 都必须拒绝。

> **概念解释｜未判定不是负例**：公开 qrels 没有列出某个 Query–passage 对，只说明该对没有出现在公开人工判断集合中；除非数据集明确发布了负标签，否则不能把“缺席”改写成“人工确认不相关”。

## 2. 审计口径与完成边界

本轮只使用：

- 官方数据页、官方仓库、固定 commit 与论文中明确的数据定义；
- 当前工作区的 SQLite、模型包、脚本和历史报告；
- 已恢复的资产对账报告。

本轮没有：

- 运行 Gate A 或 Gate B；
- 修改任何 SQLite、Qdrant 或生产 LinkRag；
- 把历史工程指标升级为论文证据；
- 把公开未标注 passage 自动标成负例；
- 开发 D1—D3、A0 或 M1；
- commit 或 push。

原计划的 T2、Lo/DRUID、C-MTEB Medical 与 Multi-CPR Medical，以及本轮追加的 T2 Train、DuRetrieval、cMedQA2/CmedqaRetrieval 实体均已落入本地忽略缓存并完成文件级核验。T2/cMedQA2 的第一层 split/exclusion 资格制品已经生成；P3-02 仍保持未完成，因为 document/version/template family 零交叉、每数据集 30-family 构造率先导、功效分母和 Internal v6 人口尚未完成。任何尚未核验的替代数据都不得仅凭网页规模视为已审计。

## 3. 权威公开数据审计

### 3.1 T2Ranking / T2Retrieval

#### 原始 THUIR 数据

- 官方仓库：[THUIR/T2Ranking](https://github.com/THUIR/T2Ranking)
- 官方数据：[THUIR/T2Ranking](https://huggingface.co/datasets/THUIR/T2Ranking)
- 建议固定 revision：[`2a369a430a70979223f1b9a41b1919774d46b432`](https://huggingface.co/datasets/THUIR/T2Ranking/commit/2a369a430a70979223f1b9a41b1919774d46b432)
- 数据许可证：Apache-2.0
- 论文 DOI：`10.48550/arXiv.2304.03679`

官方规模与格式：

| 文件 | 记录数 | 格式/语义 |
| --- | ---: | --- |
| `collection.tsv` | 2,303,643 | `pid, passage` |
| `queries.train.tsv` | 258,042 | `qid, query` |
| `queries.dev.tsv` | 24,832 | `qid, query` |
| `queries.test.tsv` | 24,832 | `qid, query` |
| `qrels.train.tsv` | 1,613,421 | TREC 四级人工 qrels |
| `qrels.dev.tsv` | 400,536 | TREC 四级人工 qrels |
| `qrels.retrieval.train.tsv` | 744,663 | 只保留检索正例的 `qid, pid` |
| `qrels.retrieval.dev.tsv` | 118,933 | 只保留检索正例的 `qid, pid` |

四级标签的官方语义是：

- `0`：完全不匹配；
- `1`：主题相关，但不能满足信息需求；
- `2`：相关并部分满足；
- `3`：精确满足并包含答案。

检索口径将 `2/3` 视为 relevant、`0/1` 视为 irrelevant。本文应同时保存原始 grade，不得只保留二值化结果。qrels 中明确为 `0/1` 的已判断 pair 可作为普通错误或不充分证据的起点；没有进入四级 qrels 的 corpus item 仍是 unjudged。

#### 已落盘文件核验

缓存根目录为 `data/robust_fusion/public/THUIR_T2Ranking/2a369a430a70979223f1b9a41b1919774d46b432/`，由 `.gitignore` 排除。官方表中的 Dev 数量实际等于含表头的物理行数；按数据行计数均少 1。正式 manifest 使用数据行数，不使用含表头行数。

| 文件 | 字节 | 数据行 | SHA-256 |
| --- | ---: | ---: | --- |
| `data/collection.tsv` | 3,659,243,528 | 2,303,643 | `07b84e543e9ba696124a727c00629d5bce586631648c436c98dd6e9b146da212` |
| `data/queries.train.tsv` | 10,210,389 | 258,042 | `b9328c8a0be4980cb8860819285ff3da8c6976f5089e0a606ff003165c4b2c0e` |
| `data/qrels.train.tsv` | 29,881,875 | 1,613,421 | `5da21371d1f2fa2700bc74a4fdc69b2389b5f304e864a42ac2fe555cad87c77e` |
| `data/qrels.retrieval.train.tsv` | 10,845,519 | 744,662 | `4a2c224021a39637873a2cd69d90a9e41cb117d0560e940399439dcc6af61cfa` |
| `data/queries.dev.tsv` | 939,767 | 24,831 | `1df544dd04bf9b6d0de0dd77e0f3a84a0d74fc4bb9a1ff67b7306de8169135ba` |
| `data/qrels.dev.tsv` | 6,537,957 | 400,535 | `a0356bd3c6d72c532ca17a4d88d7765554857f321346cf0f9cb4ad480738b25a` |
| `data/qrels.retrieval.dev.tsv` | 1,468,343 | 118,932 | `17f31db546ce3a5f861c9139939a97c19b0082a0a864be35a7821770a0705a06` |

corpus schema 是 `pid,text`；PID 从 0 到 2,303,642 连续、无空正文、无短行或非顺序 ID。其余 schema 分别是 `qid,text`、`qid,-,pid,rel`、`qid,pid`。24,831 个 Query ID 均唯一；四级 qrels 覆盖 24,827 个 Query、392,901 个 passage 与 400,535 个唯一 pair，所有 qrel PID 都存在于 corpus、所有 qrel QID 都存在于 Query 文件，grade 分布为 `0:217,692 / 1:63,911 / 2:94,364 / 3:24,568`。检索 qrels 的 118,932 个唯一 pair 与四级 qrels 中 `rel>=2` 的集合逐对完全相等；这解释了网页表中 118,933 与 C-MTEB 118,932 的一项差异是表头计数，不代表丢失一条正例。原始版与 C-MTEB 派生版的 Query/PID/pair 差异已在下文通过逐 ID 审计完整解释。

Train 的 258,042 个 Query ID 唯一、无空文本，与 Dev Query ID 交集为 0。四级 Train qrels 有 1,613,421 个唯一 pair，grade 分布为 `0:699,080 / 1:169,679 / 2:415,994 / 3:328,668`，所有 QID/PID 都存在于对应 Query/corpus。检索正例文件的 744,662 个 pair 与四级 qrels 中 `rel>=2` 的集合完全相等；它们覆盖 200,376 个 Query，另有 57,666 个已判断 Query 没有 `rel>=2` pair。

**纳入判断**：纳入中文通用公开主数据候选。原始 Dev 整体标记为 calibration/exposed-only；正式 Gate A 与 Blind 候选只能使用原始 230 万 corpus 和 Train 四级 qrels，再按 Query/document family 物理分开。原始 Test 在该固定实体中没有公开 qrels，不负责提供备用确认路径。四级 relevance 仍需二次映射为目标事实关系。

#### C-MTEB 紧凑派生版

- corpus/query revision：[`8731a845f1bf500a4f111cf1070785c793d10e64`](https://huggingface.co/datasets/C-MTEB/T2Retrieval/commit/8731a845f1bf500a4f111cf1070785c793d10e64)
- qrels revision：[`1c83b8d1544e529875e3f6930f3a1fcf749a8e97`](https://huggingface.co/datasets/C-MTEB/T2Retrieval-qrels/commit/1c83b8d1544e529875e3f6930f3a1fcf749a8e97)
- corpus 118,605，queries 22,812，qrels 118,932；
- data schema：`id:string, text:string`；
- qrels schema：`qid:string, pid:string, score:int64`；所有公开 score 均为 `1`。

118,605 个 corpus 文档全部也是至少一个 Query 的 relevant 文档。它实质上是由正例关系裁出的紧凑池，而不是原始 230 万背景语料。它可以作为已知正例、等价候选和内容对齐种子，但不能单独承担候选生成与负例解释。

#### 已落盘与逐行 provenance 核验

| 实体/revision | 文件 | 字节 | 行数 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| T2Retrieval `8731a845…` | `data/corpus-00000-of-00001-8afe7b7a7eca49e3.parquet` | 156,789,043 | 118,605 | `d4a207a9277eb1cf31f68ab6a7236cbf3e8fbf9493e0e2b577a34660929fcd17` |
| T2Retrieval `8731a845…` | `data/queries-00000-of-00001-930bf3b805a80dd9.parquet` | 817,492 | 22,812 | `47a5866f1e668700420f44b200f9808c9e799208a46da147dfe380b40fb406ec` |
| T2Retrieval-qrels `1c83b8d…` | `data/dev-00000-of-00001-92ed0416056ff7e1.parquet` | 1,146,734 | 118,932 | `a283ce5c8bd739e7f5524107586eb21e68d7736172524b79eb5bd844c4b78c00` |

三个 parquet 均无 null；corpus/query ID 与正文分别全唯一，qrels 的 118,932 行均为唯一 `qid,pid` pair 且 `score=1`。与已落盘原始 T2 做逐 ID、逐 pair、逐文本核对后得到：

- 22,812 个 C-MTEB Query ID **恰好**是原始 Dev 四级 qrels 中至少有一条 `rel>=2` 的 Query 集，Query 文本 0 处不一致；
- 118,605 个 C-MTEB corpus ID **恰好**是这些正 qrels 涉及的 passage 集，正文 0 处不一致；
- 118,932 个 C-MTEB qrel pair 与原始四级 qrels 的 `rel>=2` pair 集完全相等；
- 网页所列原始 118,933 是含表头物理行数，实际正例数据行是 118,932；不存在丢失一条正例的问题。

因此 C-MTEB T2 的实际派生规则已由实体级对账恢复为“原始 Dev 的正 qrels 投影”：保留全部 `rel>=2` pair，以及它们覆盖的 Query 和 passage。它可作为低成本正例/内容对齐制品，但仍不是含负例背景的完整检索 corpus；正式候选生成继续使用原始 T2。

### 3.2 MedicalRetrieval / Multi-CPR

#### 原始 Multi-CPR

- 官方仓库：[Alibaba-NLP/Multi-CPR](https://github.com/Alibaba-NLP/Multi-CPR)
- 固定 commit：[`a4e467182a3e2c110528a1575d79b33cc449d2c3`](https://github.com/Alibaba-NLP/Multi-CPR/commit/a4e467182a3e2c110528a1575d79b33cc449d2c3)
- 论文 DOI：`10.1145/3477495.3531736`
- 数据许可证：**未知**。固定 commit 未见 `LICENSE`，README 未声明数据许可，GitHub repository metadata 的 license 也为 null。

官方固定 commit 中 Medical 原始语料由四个 `corpus_split_*.tsv` 组成。实际拼接后共有 960,526 条、960,526 个唯一 PID：`1–959,526` 连续背景/训练语料，加上 `30,000,001–30,001,000` 的 1,000 条 Dev 正例。训练 Query/qrels 各 99,999 行，Dev Query/qrels 各 1,000 行；qrels 格式是 `qid, 0, pid, 1`，最终每 Query 一个正例。训练 qrels 的 99,999 行覆盖 98,872 个唯一 PID，说明不同 Query 可以共享正例。论文描述的标注过程虽然比较过候选并剔除部分回答，但这些负判断没有随最终公开 qrels 发布。

四个 corpus 文件是按字节连续切分，文件边界可落在 UTF-8 字符或 TSV record 中间；不能把每个分片当成独立 UTF-8 TSV 读取，必须按 `1→4` 顺序做增量解码或先按字节逻辑拼接。按该规则核验后，语料无重复 PID、冲突 PID、空正文或格式错误。

已落盘文件：

| 文件 | 字节 | 逻辑行/物理行 | SHA-256 |
| --- | ---: | ---: | --- |
| `corpus_split_1.tsv` | 87,570,784 | 物理换行 240,225 | `6fe98d704da0f294b6033855c0f927e8c814292fbf4a2be00cb78cd4f63d7a64` |
| `corpus_split_2.tsv` | 87,570,784 | 物理换行 240,025 | `10e31087c1bc3321906711051000875f16083c51badc40524acd900ba3a4af77` |
| `corpus_split_3.tsv` | 87,570,784 | 物理换行 240,244 | `c2e816e7f68e4db1e44a74d35a84f2c0e49e2a3fddb7d4c178d26d198cd692c3` |
| `corpus_split_4.tsv` | 87,570,786 | 物理换行 240,032 | `4bb31d3220c2684a24c104bc1c30f43a35771d87ab96ea4546bfa42aece820a7` |
| `train.query.txt` | 5,678,463 | 99,999 | `8cda9b79e068f013db11e971b04c66aa48c32319d36dd861eaa56725a23694e6` |
| `dev.query.txt` | 57,652 | 1,000 | `a7aa0671305f4c2fc3e65376b1eb703fccb4f35d430b666c4a42b5ff85a40af1` |
| `qrels.train.tsv` | 1,677,422 | 99,999 | `e19f1efc176fa816f6b2d3bc94b6175ee1c1edb55989771605a4a3d371587d81` |
| `qrels.dev.tsv` | 16,893 | 1,000 | `0aba3916c4dd654e4d8b1ba828a691d20f0fc397f233630f2dbc95c68c2b9cba` |

四个分片的物理换行数之和也是 960,526，但这不代表分片可独立解码；正式 loader 必须有跨分片 UTF-8/record 契约测试。

因此：

- 单一正例可作为目标参照种子；
- 其他 corpus passage 只能视为未判定；
- 不能从 qrels 缺席派生事实冲突、普通负例或 false negative；
- 医疗事实的版本、时效、适用条件和专业正确性必须由合格证据或人工复核确认。

#### C-MTEB 派生版

- corpus/query revision：[`2039188fb5800a9803ba5048df7b76e6fb151fc6`](https://huggingface.co/datasets/C-MTEB/MedicalRetrieval/commit/2039188fb5800a9803ba5048df7b76e6fb151fc6)
- qrels revision：[`37b8efec53c54c3d9c6af212f6710b62ccdf895c`](https://huggingface.co/datasets/C-MTEB/MedicalRetrieval-qrels/commit/37b8efec53c54c3d9c6af212f6710b62ccdf895c)
- corpus 100,999，queries 1,000，qrels 1,000；
- data schema：`id:string, text:string`；
- qrels schema：`qid:string, pid:string, score:int64`；恰好每 Query 一个 `score=1`。

当前 card 没有 license，也没有说明 100,999 passages 如何从原始 960,526 passages 选出；本轮通过逐 ID/正文对账恢复了实际规则。

已落盘核验结果为：

| 实体/revision | 文件 | 字节 | 行数 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| MedicalRetrieval `2039188…` | `data/corpus-00000-of-00001-ee9a640f70deeff5.parquet` | 25,029,508 | 100,999 | `12396859662981d743670222d6805c5cadfd0e54d13dcb60afe3fe99e6fa836d` |
| MedicalRetrieval `2039188…` | `data/queries-00000-of-00001-eeb3bbcd890c48b3.parquet` | 48,473 | 1,000 | `902c339479228740210e96db9c119ebc82cb19b18942e5352e8c9a58431ee8a0` |
| MedicalRetrieval-qrels `37b8efe…` | `data/dev-00000-of-00001-e80499fb7880bec9.parquet` | 12,201 | 1,000 | `e240f2ce1be409b5e0ab5efae8af9a8387d0fdca7abe37a3bb499b081be8c544` |

三份 parquet 均无 null；corpus ID 全唯一，但 100,999 个 ID 对应 100,986 个唯一正文，即存在 13 条文本重复。逐 ID/正文对照原始 Multi-CPR 后，派生规则已恢复：

- corpus **恰好**是原始 PID `1–99,999` 的前缀，加上全部 1,000 个 Dev 正例 PID `30,000,001–30,001,000`；100,999 条正文与原始同 PID 文本 0 处不一致；
- 该前缀只覆盖 98,872 个唯一训练正例 PID 中的 10,250 个，所以它不是训练正例并集，也不是完整 960,526 passage corpus；
- 1,000 个 Dev Query ID 与原始文件一致；999 条文本逐值一致，QID 653 只删除了原文末尾一个全角空格 `U+3000`；
- 1,000 个 qrel pair 与原始 Dev qrels 逐对完全一致，全部 `score=1`。

因此“如何选出 100,999 passages”的实体 provenance 已解决，但两个科学/合规问题仍在：它是人为截取的 corpus 前缀，负例分布不代表完整 Medical；原始及派生数据仍没有明确许可证。若获授权，正式候选生成优先使用完整原始 960,526 corpus，而不是该前缀池。

**纳入判断**：暂不冻结为 Gate A 必要单元。只有在获得明确的数据许可/授权、派生规则和逐行 provenance 后，才能把它升级为条件纳入。若不能及时澄清，应在 Gate A 封存前替换数据集，而不是让一个许可未知的数据集导致必要单元不可估计。

### 3.3 Lo/DRUID

- 官方数据：[Lo/rerankers-and-lexical-similarities](https://huggingface.co/datasets/Lo/rerankers-and-lexical-similarities)
- 固定 revision：[`4b37ea52c1e1ad5af63a4feee9ce1cfb7348078b`](https://huggingface.co/datasets/Lo/rerankers-and-lexical-similarities/commit/4b37ea52c1e1ad5af63a4feee9ce1cfb7348078b)
- 数据许可证：MIT；配套代码仓库为 GPL-3.0，二者必须分开记录。
- 论文 DOI：`10.18653/v1/2025.fever-1.2`
- 上游核对源：[copenlu/druid](https://huggingface.co/datasets/copenlu/druid)，revision [`d3f49c237d7d99870f97df51ac52e4f5e16f5cb6`](https://huggingface.co/datasets/copenlu/druid/commit/d3f49c237d7d99870f97df51ac52e4f5e16f5cb6)，MIT。

`DRUID/standard` 有 875 个唯一样本，每个样本 2–5 个 passages，字段为：

```text
ids
claim_id
question
chunk_sources
is_gold_chunk
chunk_dates
chunk_stances
chunks
is_helpful_chunk
```

同一批 875 个样本另有 `title` 和 `prompt` 变体；三个 split 不能当成 2,625 个独立 Query。主复现只用 `standard`，其余只作配对敏感性分析。

字段语义边界：

- `chunk_stances` 是候选相对 claim 的支持、反驳或多种 `insufficient-*`；
- `is_helpful_chunk` 表示候选 stance 足以帮助给出事实核查 verdict；
- non-helpful / `insufficient-*` 表示证据不足，不等于事实错误；
- `is_gold_chunk` 表示来自原事实核查站点的原始证据来源，不表示该 passage 必然正确、相关或与目标证据等价；
- 当前 card 文本提及 `gold_chunk_ix`，但 pinned viewer 的实际 schema 是 `is_gold_chunk` 与 `is_helpful_chunk`，正式 intake 必须以文件 schema 为准。

#### 已落盘文件核验

缓存根目录为 `data/robust_fusion/public/Lo_rerankers-and-lexical-similarities/4b37ea52c1e1ad5af63a4feee9ce1cfb7348078b/`：

| 文件 | 字节 | 数据行 | SHA-256 |
| --- | ---: | ---: | --- |
| `README.md` | 3,423 | 不适用 | `fc2844114c26c0bed821fef5d2fd85d9b9bb6a222728dd665a9afba07dc54059` |
| `DRUID/chunks.jsonl` | 3,327,953 | 875 | `679850fd833ca6b84f1751927c7048758be6dd1645bfd4932b8af90a57d5f79a` |

875 行 JSON 均可解析且键集合完全一致；`claim_id`、question 与样本级 `ids` 均为 875 个唯一值。每行所有 passage 级列表长度完全一致，2/3/4/5 passage 的样本数分别为 83/168/336/288，共 3,454 个 passage ID 且全部唯一；正文无空值，3,439 个唯一正文。stance 分布为 `supports:573 / refutes:1,266 / insufficient-supports:481 / insufficient-refutes:394 / insufficient-neutral:740`；`is_gold_chunk=True` 706 条，`is_helpful_chunk=True` 1,839 条。上述统计只验证文件结构与标签分布，不把 stance/helpful/gold 自动映射为本研究事实真值。

**纳入判断**：纳入英文 RQ1/RQ2 现象和构件复现层，不进入 T2、Medical/替代集、Internal v6 组成的六单元 C1 主分母，也不进入 Gate B。DRUID 的 2–5 个候选是既有预选候选，不是本文三路召回总体，因此不能检验 C3。

### 3.4 DuReader Retrieval / C-MTEB DuRetrieval（独立数据集）

- 上游官方仓库：[baidu/DuReader](https://github.com/baidu/DuReader)，审计 commit `c625076b06da8f56d59f19c41c73bd580a98a347`；
- 上游仓库许可：Apache-2.0；官方 DuReader Retrieval 说明的原始规模为 90,000 以上 Query 与约 8 百万 passage；
- C-MTEB data revision：[`a1a333e290fe30b10f3f56498e3a0d911a693ced`](https://huggingface.co/datasets/C-MTEB/DuRetrieval/commit/a1a333e290fe30b10f3f56498e3a0d911a693ced)；
- C-MTEB qrels revision：[`497b7bd1bbb25cb3757ff34d95a8be50a3de2279`](https://huggingface.co/datasets/C-MTEB/DuRetrieval-qrels/commit/497b7bd1bbb25cb3757ff34d95a8be50a3de2279)。

DuRetrieval 是一个独立数据集实体；“DuRetrieval 文本出现在 C-MTEB Cmedqa compact corpus 中”不使两个数据集成为同一数据集。已落盘的 C-MTEB DuRetrieval 实体为紧凑派生版，不是官方 8 百万 passage 全量语料：

| 实体/revision | 文件 | 字节 | 行数 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| DuRetrieval `a1a333e…` | `data/corpus-00000-of-00001-19b9e924cb33e4d5.parquet` | 64,412,709 | 100,001 | `d4b4eb51b63549ef0851a15fc63c2a61b703dce95e3727b535a08f7ba1d14424` |
| DuRetrieval `a1a333e…` | `data/queries-00000-of-00001-7c7edb40be6b560c.parquet` | 118,461 | 2,000 | `62ac55e764bffd4ffceb0aa51e7a536a0e5932f23c8606566906db6a9efb4b94` |
| DuRetrieval-qrels `497b7bd…` | `data/dev-00000-of-00001-d3c385852a7c0c9d.parquet` | 420,443 | 9,839 | `c87e7c16f535a98b29ee0ebf6977639c793e3bd149c04634a1810273cfd3c3e5` |

corpus/query 分别有 100,001/2,000 个唯一 ID 与唯一非空文本；9,839 个 qrel pair 全部唯一、`score=1`、QID/PID 全部有效。每 Query 有 1–31 个正例，1,799/2,000 个 Query 是多正例。但 C-MTEB card 没有给出从原始 8 百万语料到 100,001 条的生成规则和独立许可字段，所以 Apache-2.0 只能记为上游仓库许可，不自动代替派生实体的 provenance 审计。

**纳入判断**：完整保留为独立中文公开数据。当前冻结对象是上述 pinned C-MTEB compact revision 的 corpus、Query、qrels 三实体，不从 Cmedqa 重合关系中扣除任何行，也不与 cMedQA2 合并。由于其功能角色与 T2 高度重复，当前预先指定为六单元 C1 主分母和 Gate B 之外的辅助稳健性数据；它不是数据不足或结果不利时可切换的备用 Gate 路径。若以后要让它承担确认性主单元，必须在结果不可见时另升协议版本，并先明确是继续使用 compact 实体还是取得上游约 800 万 passage 全量语料。

### 3.5 cMedQA2 / C-MTEB CmedqaRetrieval

#### 上游 cMedQA2 原始数据

- 官方仓库：[zhangsheng93/cMedQA2](https://github.com/zhangsheng93/cMedQA2)；
- 固定 commit：`85feb9278c3ae552c591205cbf3e828368c91f8f`；
- 使用边界：README 明确为 **non-commercial research**，数据已匿名化；仓库 `LICENSE` 是 GPL-3.0；
- 论文 DOI：`10.1109/ACCESS.2018.2883637`。

已按固定 commit 落盘全部原始问题、回答和三个 candidate split：

| 文件 | 字节 | 解压后记录 | SHA-256 |
| --- | ---: | ---: | --- |
| `README.md` | 1,771 | 不适用 | `5a72f9c5eca7927be95760875ae1399d9bde4f44cd43ab74159a5abd2df7b9fe` |
| `LICENSE` | 35,149 | 不适用 | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` |
| `question.zip` | 7,701,487 | 120,000 个 question | `df4738599e20deed824757c40f78c5a3b752b262d2c730de72d69449d95daa89` |
| `answer.zip` | 27,610,046 | 226,266 个 answer | `5fd8ba9f049e419929ff3526e7b6902aaa2caba43cf207ea086b1d7755394485` |
| `train_candidates.zip` | 23,740,116 | 5,000,000 个训练 triplet | `e3219cfcd5fe0e84e926e815c2029e494ef776520ef32b09f2a24dc3cbac9ab1` |
| `dev_candidates.zip` | 2,395,726 | 400,000 个带 `0/1` 标签 pair | `3301b55cddbdd512f6960fb4ed72fd27c7b00db2ed3f10e88d0c2764263a379e` |
| `test_candidates.zip` | 2,394,296 | 400,000 个带 `0/1` 标签 pair | `d358f5d6b5711a39942e3798f45b5a66887393d1858e88aa1953925e0b630c07` |

120,000 个 question ID 和 226,266 个 answer ID 均唯一、无空文本；分别对应 119,397 个唯一问题文本与 196,892 个唯一回答文本。candidate split 核验结果为：

| split | Query ID | candidate 记录 | 正例关系 | 负例关系/语义 |
| --- | ---: | ---: | ---: | --- |
| Train | 100,000 | 5,000,000 triplet | 188,490 个唯一 `qid,pos_ans_id` | 每行另给出 `neg_ans_id`；负回答 ID 并集覆盖全部 226,266 个 answer |
| Dev | 4,000 | 400,000 pair | 7,527 个 `label=1` | 392,473 个 `label=0` |
| Test | 4,000 | 400,000 pair | 7,552 个 `label=1` | 392,448 个 `label=0` |

所有 candidate QID/answer ID 都存在于上游 CSV，Dev/Test 的 label 只有 `0/1`。三个 split 的 Query ID 交集均为 0，但在 Unicode NFKC、首尾空白删除和连续空白折叠后，问题文本 family 在 Train×Dev、Train×Test、Dev×Test 间分别重合 35/46/1 个；合并后共有 80 个跨 split family，涉及 Train/Dev/Test 的 106/35/46 个 Query。三个 split 的正例 answer ID 两两交集均为 0。正式资格规则因此不能只信上游 split 名称：原始 Dev 全部 calibration/exposed-only，任何跨 split Query family 全部排除，剩余 Train 99,894 个 Query 和 Test 3,954 个 Query 分别只是 Gate A/Gate B 资格母池。上游 `label=0` 是“对该问题的非匹配回答”的直接已标负例，但仍不等于本研究的 `factual_conflict`；医疗正确性、时效性、适用条件和等价关系仍需聚焦人工复核。

#### C-MTEB 紧凑派生版

- data revision：[`cd540c506dae1cf9e9a59c3e06f42030d54e7301`](https://huggingface.co/datasets/C-MTEB/CmedqaRetrieval/commit/cd540c506dae1cf9e9a59c3e06f42030d54e7301)；
- qrels revision：[`279d737f36c731c8ff6e2b055f31fe02216fa23d`](https://huggingface.co/datasets/C-MTEB/CmedqaRetrieval-qrels/commit/279d737f36c731c8ff6e2b055f31fe02216fa23d)。

| 实体 | 文件 | 字节 | 行数 | SHA-256 |
| --- | --- | ---: | ---: | --- |
| CmedqaRetrieval | corpus parquet | 60,791,899 | 100,001 | `15191de1c0568805e536d5eb4f4233e105b819390ae816d88d42102f89b5261a` |
| CmedqaRetrieval | queries parquet | 527,508 | 3,999 | `ffa5d51ae6fed9de058fca0842cdb30d7c7e3a252e8ccb868c9c2710a06c3f4c` |
| CmedqaRetrieval-qrels | Dev parquet | 404,005 | 7,449 | `4d104c611091a9d366c4b279a92a6849565529761253cd91003af99e0608d387` |

这三个 parquet 本身无 null、ID 与 pair 均唯一，qrels 全部 `score=1`；但实体级对账表明它不是纯 cMedQA2 corpus。`scripts/audit_cmedqa_corpus_provenance.py` 在固定输入 SHA-256 上生成了 `ROBUST-FUSION-CMEDQA-PROVENANCE-PEEL-2026-08-28-v2`，逐条只输出 ID/hash 和上游 crosswalk，不输出正文；同一 manifest 还独立核验 DuRetrieval corpus/Query/qrels 三实体的完整性：

- 88,242 个 passage 只与 C-MTEB DuRetrieval 正文完全一致；
- 7,137 个 passage 只与上游 cMedQA2 answer 正文完全一致；
- 2,086 个 passage 同时在两者出现，不能排他地归因于任一来源；
- 2,536 个 passage 与两份 pinned 比较源均无原文精确匹配，只能记 `unresolved_neither`；
- 因而 DuRetrieval 任意精确匹配仍是 90,328，cMedQA2 answer 任意精确匹配仍是 9,223；其中包含 7,165/7,321 个 qrel passage ID；
- 3,999 个 Query 中 3,985 个能通过精确正文 hash 直接对上上游 cMedQA2 question；
- C-MTEB 与原始 Dev 在去重后都有 7,449 个正例文本 pair，但只有 7,262 个精确正文 pair 一致，对称差集为 374；当前 card 没有解释这些文本变换和 90,328 个 DuRetrieval 精确匹配 passage。

这里的“精确”是 parser 返回 Unicode 字符串的原样 UTF-8 内容相等；没有大小写、空白、Unicode 或模糊归一化。`both_exact` 不得强制单归因。2,536 条 `unresolved_neither` 全部保持一个未解析审计类；qrel 关联不产生子类或后续动作，不再尝试归一化/模糊回配，不安排专项标注，不删除，也不用于正式语义计算。该类仍不能证明记录与 cMedQA2 无关，只表示当前不继续处理其来源归属。

社区 issue 已公开提出 C-MTEB Cmedqa 生成规则与标签问题；该 issue 只是待解的风险信号，不是官方裁定。本轮逐实体对账已独立确认“混合 DuRetrieval 背景”这一数据事实，因此不将 C-MTEB 紧凑版当成医疗语料的权威文本来源。

**纳入判断**：研究负责人已确认非商业科研与保守治理边界，现以上游 cMedQA2 原始实体正式替换许可不明的 MedicalRetrieval，并排除 C-MTEB Cmedqa 紧凑混合 corpus 承担确认性候选生成。该选择固定数据角色和资格方向，不等于最终样本分母已经封存。

## 4. 本地资产审计

### 4.1 当前可复用资产

| 资产 | 当前覆盖 | 可复用内容 | 不能替代的内容 |
| --- | --- | --- | --- |
| `runs/linkrag_eval.sqlite3` | 22 个 dataset 条目；21 个有语料；49,774 Chunk；51 run；2,884 aggregate metric | content hash、doc/chunk 映射、历史运行配置；逐数据集验证后才能复用正文 | `eval_query=0`、`eval_qrel=0`；没有逐 Query candidate/route snapshot；`990126/990127` 正文已证实不是可直接复用的权威文本 |
| `runs/bm25_eval.sqlite3` | 31,072 Chunk，11 个 dataset | 新 Query 到位后重算 BM25 | 无 Query/qrels，无历史 score/rank；覆盖不含全部公开主数据 |
| `runs/alt_embedding_eval.sqlite3` | 20,772 Chunk，9 个 dataset，全为 1024 维 BAAI/bge-m3 | 仅解释历史相似性资产和研究动机 | BGE-M3 已被研究负责人淘汰；即使模型名看似一致，也不得复用向量、筛选正式候选或进入独立审计 |
| 当前 eval Qdrant | 权威对账报告核验 44,773 points | 现有 Chunk 的 dense/sparse 资产 | 不是 Query 级三路冻结快照；P4-00 与 contract-lock 前不能承担确认性运行 |
| LTR-v3 模型包 | 38 个三路分数、排名、差异与表面约束特征 | Gate A/B 的强基线制品 | 原始训练数据、OOF 和 candidate cache 不在当前 checkout；需 current-HEAD 契约重放 |

### 4.2 不能进入确认性分析的历史资产

- 当前 `runs/` 只有三份 SQLite；`runs/golden_v2`、`runs/robust_fusion`、`.specs` 和报告引用的行级 candidate/qrels 文件均不存在。
- 报告索引中的 700 个 `runs/...` 机器产物链接在当前工作区存在数为 0。历史报告能证明曾经执行过，但不能恢复行级真值。
- Blind v4/v5 已揭盲；其 T2 Query 和 structured Query 只能作研究动机，不能改名进入 Gate A/B。
- `990123/990124/990126/990127` 虽有公开风格 corpus，但 `ingestion_ref`、revision、license、note 均为空，不能凭数据集名称推断它就是本研究计划的正式公开数据。
- 当前三个历史 T2 dataset 的 `source_passage_id` 是本地 `spark-*` ID，不能直接回连官方 pid；必须下载官方实体后按内容/hash 对齐。

#### `990126/990127` 官方 ID—正文对账

`990126=dureader_800_v2` 和 `990127=cmedqa_800_v2` 各有 800 条。将 SQLite `source_passage_id` 分别与本轮 pinned C-MTEB DuRetrieval/CmedqaRetrieval corpus 逐 ID 比较得到：

| dataset | SQLite 记录 | 官方 ID 命中 | 正文完全一致 |
| --- | ---: | ---: | ---: |
| `990126` | 800 | 800 | 0 |
| `990127` | 800 | 800 | 0 |

SQLite 正文可见典型乱码字节序列，且没有可证明原始编码和转换链的 ingestion manifest。这不能仅通过“尝试转回 UTF-8”就宣称修复。本轮没有修改 SQLite；两组历史记录只保留 `source_passage_id`、dataset 身份、索引覆盖和曝光对齐价值，正式候选生成必须使用本轮 pinned 官方文件的正文。

### 4.3 泄漏与家族隔离风险

49,774 个 Chunk 只有 48,439 个唯一 `content_hash`，即有 1,335 条重复记录。已发现的重要跨集重合：

- T2 历史集 `993101 × 993103`：860 条；
- `993100 × 993101`：185 条；
- `993100 × 993103`：16 条；
- `990126 × 990127`：285 条。

因此 Dev、GateA、GateB 必须至少按 `content_hash + document family + counterfactual template family` 聚类隔离，不能只按 dataset_id 或 query_id 随机切分。

### 4.4 复用—曝光—确认性资格台账

> **概念解释｜可复用不等于可确认**：一个 corpus、索引或向量可以帮助重新生成候选，但只要 Query 已揭盲、候选池由已揭盲 Query 条件化，或标签缺少可追溯来源，它就不能直接承担确认性结论。

| 资产 | 曝光状态 | 允许复用 | 确认性资格 | 必要排除/前置 |
| --- | --- | --- | --- | --- |
| 原始 T2Ranking 230 万 corpus 与 Train 四级 qrels | 已曝光来源均是 Dev 投影；Train 与 Dev QID 交集为 0 | 正式 T2 候选生成、原始 relevance、完整背景语料 | **条件合格** | 原始 Dev 整体 calibration/exposed-only；GateA/Blind 只从 Train 按 family 再分；Seal 前新发现的 Train 曝光必须追加排除 |
| C-MTEB T2 正例投影 | Blind v4/v5 的直接来源，恰好是原始 Dev 正例投影 | 正例/PID/正文对齐、曝光恢复 | **不单独合格**为完整检索 corpus | 原始 Dev 全排除出确认性 cohort；不得把正例投影当背景语料 |
| SQLite `993101/993103` | 由已揭盲 Query 条件化构造，结果已观察 | 曝光恢复、内容对齐和历史工程审计 | **不合格**作为 Gate A/B 候选池 | 不能把两个 10k 子池改名复用；正式 T2 必须回到完整原始 corpus |
| SQLite 其他 corpus 与 BM25/Alt/Qdrant | 多数参与过历史工程开发；无研究 Query/qrels | 作为 Internal v6 的候选背景、去重种子或计算缓存 | **条件合格**为工程输入，不是真值 | 逐数据集验证正文；`990126/990127` 只用 ID/provenance；新 Query/标签独立生成；完成 P4-00 与精确 manifest |
| 旧 eval MySQL 与历史 aggregate run | 已用于历史开发，且只有聚合结果 | 验证分享包 provenance、预算与工程动机 | **不合格**为确认性证据 | query/qrel 均为 0；不得从 aggregate metric 反推样本级结论 |
| `ssh linkcv` 中间件主机 | 未部署 LinkRag-Eval，未发现研究行级资产 | 只提供远端中间件服务 | **无数据资格** | 不再把服务器文件系统作为 qrels/candidate 恢复源 |
| Multi-CPR/C-MTEB Medical | 本轮新摄取，未发现本项目历史确认性运行 | 获授权后的候选构造与单正例种子 | **许可阻塞** | 明确许可/授权、医疗证据复核；优先完整 960,526 corpus |
| 上游 cMedQA2 | C-MTEB 与 SQLite 历史资产可能曝光过 Dev 文本；Train/Test 行级尚未用于本研究结果 | 原始问题、回答、已标正/负 candidate 与医疗术语密集数据 | **已选定，待分母封存** | Dev 全部 exposed-only；跨 split Query family 全排除；Train/Test 分别为 Gate A/Gate B 资格母池；不重分发全文；医疗事实仍人工复核 |
| C-MTEB Cmedqa 混合 corpus | 其 Dev 投影与历史 `990127` 有 ID 交集，本地文本已乱码 | 只作四类 ID/hash provenance 与曝光 crosswalk | **不合格**为医疗候选生成 corpus | 88,242 Du-only / 7,137 cMedQA2-only / 2,086 both / 2,536 统一 unresolved；不按 qrel 细分或处理 |
| C-MTEB DuRetrieval | 本轮新摄取；历史 `990126` 与其有 800 个 ID 交集但本地文本乱码 | 完整 pinned corpus/Query/qrel 与辅助稳健性分析起点 | **完整独立保留**，当前不进主 Gate | 100,001/2,000/9,839 三实体零删减；功能角色与 T2 重复，角色变化须 Gate 前另升协议 |
| Lo/DRUID `standard` | 本轮新摄取，未发现本项目历史运行 | 英文 RQ1/RQ2 构件与现象复现 | **仅外部复现合格** | 不进入六单元 C1 主分母、C3 或 Gate B |

T2 曝光恢复制品位于被 `.gitignore` 排除的 `data/robust_fusion/derived/exposure/`：

- `t2_blind_v4_exposed_qids_exact.txt`：800 行，SHA-256 `3d8ab999a09624ffd442f7e0af4c6f886b1efa710b9726f130d44f27c2ef61bb`；按历史固定 hash 顺序重放后，生成的 10,000 PID 与 SQLite `993101` 逐位完全一致。
- `t2_blind_v5_exposed_qids_conservative.txt`：502 行，SHA-256 `5f0c133a949022d6b72e658fdb146eb7ade83c2314d6889f5ec1055465574a13`；SQLite `993103` 按 `doc_id` 排序的前 2,307 个 PID 是严格字典序正例前缀，覆盖报告所述 2,307 个正例。两个 PID 各被两个 QID 共享，所以实际 500 个 QID 只能恢复为 502 项保守超集。
- `t2_confirmatory_exclusion_qids_conservative.txt`：1,302 行，SHA-256 `f92f25555344cdfd75ab18f3da36b07cbc11cfc6f11d922ba14f0d81e51262e2`；v4 与 v5 保守集交集为 0。
- `t2_exposure_manifest.json`：记录输入 revision、文件摘要、SQLite 摘要、恢复算法和两组歧义；SHA-256 `f937407423b722610b1467398c24e59bcea035339a24e2c87ef5e052307a4df2`。

Blind v5 报告同时记载“排除此前曝光的 811 个 source record”。其中 v4 的 800 个已恢复，另外 11 个的行级文件、QID 与 query text 均不在 SQLite、分享包、当前服务器或当前 checkout。本轮没有伪造这 11 个身份，而是用更严的 split-level 规则覆盖其残余风险：所有可审计的历史 T2 来源都是 C-MTEB/原始 Dev，故整个原始 Dev 排除出确认性 cohort，GateA/Blind 候选只从与 Dev QID 交集为 0 的原始 Train 再分。该规则必须在 P3-02 与数据集分母一起封存；若封存后才发现反例，不得补排除后继续声称原 cohort 有效。

## 5. 数据覆盖—标签覆盖—研究缺口矩阵

| 数据/资产 | Corpus | Query | 原始 qrels/labels | 可直接使用 | 可自动派生 | 只能人工确认 | 确认性角色 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T2 原始 | 完整 230 万 | Train 258,042；Dev/Test 各约 24,832 | Train/Dev 四级 qrels；固定实体无 Test qrels | Query、passage、已判断 relevance、明确 `0/1` 普通错误起点 | 三路候选、route score/rank、相似度、content-family、疑似漏标优先级 | 等价组、事实冲突、unknown、未判断项真值 | **正式主数据集**；Dev 整体 calibration/exposed-only，GateA/Blind 只从 Train 再分 |
| C-MTEB T2 | 118,605 正例并集 | 22,812 | 118,932 个二值正例 | 正例种子与内容对齐 | 参照集合候选 | 不能从缺席派生负例 | 只作种子；**不单独承担 Gate A corpus** |
| Multi-CPR Medical | 960,526 | Dev 1,000；固定仓库未提供独立 Test 文件 | 每 Query 单一正例 | 完整匹配参照种子 | 三路候选、高相似候选、专业词项匹配 | 全部等价/冲突、漏标、时效和专业正确性 | **退出当前确认性分母**；仅保留审计/未来独立扩展 |
| C-MTEB Medical | 100,999 | 1,000 | 每 Query 一个 `score=1` | 低成本正例种子 | 候选筛选 | 同上 | **退出当前确认性分母**；派生规则仅作追溯 |
| 上游 cMedQA2 | 226,266 answer ID；196,892 个唯一回答文本 | Train 100,000；Dev/Test 各 4,000 | Train triplet；Dev/Test 各 400,000 个已标 `0/1` pair | 固定问题/回答、明确正负 answer-selection 标签 | 三路候选、高相似/疑似漏标优先级、family 去重 | 事实正确性、等价/冲突、时效与适用条件；医学域只作分层属性 | **正式替代 Medical**；Dev/跨 split family 排除后待封存最终分母 |
| C-MTEB Cmedqa | 100,001：88,242 Du-only / 7,137 cMedQA2-only / 2,086 both / 2,536 统一 unresolved | 3,999 | 7,449 个正例 | 四类 ID/hash provenance 与曝光 crosswalk | 不从未文档化混合 corpus 派生负例；不细分 unresolved | 不安排该 2,536 条的来源追认 | **排除作为医疗确认性 corpus** |
| C-MTEB DuRetrieval | 完整 pinned compact corpus 100,001 | 2,000 | 9,839 个正例 | 全量 Query/PID/qrel；零重合扣除 | 辅助分析中的三路候选和相似筛选 | 未标项与事实关系只在另行预注册分析中聚焦确认 | **独立完整辅助数据**；不进当前六单元 Gate，不是备用通过路径 |
| Lo/DRUID standard | 每 Query 固定 2–5 候选 | 875 | stance/helpful/gold/source/date | claim-relative stance、helpfulness、来源与日期 | target-alignment 待复核标签、相似度、Reranker 复现 | 正确目标对齐、等价组、冲突类型、时态/条件边界 | 英文 RQ1/RQ2 外部复现；**不进六单元分母** |
| 本地主 SQLite corpus | 49,774 Chunk | 0 | 0 | ID/hash/doc 映射；正文需逐集验证 | 官方 ID 对齐、去重、family 聚类 | 全部研究关系标签 | 工程输入，不是真值；`990126/990127` 正文不可用 |
| BM25/Alt/Qdrant | 部分 corpus | 0 | 0 | BM25/Qdrant 的索引与向量缓存；Alt 为历史 BGE sidecar | 新 Query 只按已锁定的真实三路重算 | 无法自动生成真值 | 工程加速，不是真值；历史 BGE 不复用 |
| 历史报告/Blind | 报告级聚合 | 行级文件缺失且已曝光 | 不可复核 | 动机、预算和候选构造率先验 | 不能恢复确认性 qrels | 找回备份后也只可用于 Dev 审计 | **排除 Gate A/B** |

## 6. 推荐纳入、替换与排除方案

### 6.1 立即保留

1. **T2 原始版**：作为中文通用正式主数据集。已落盘完整 corpus、Train/Dev Query 和四级/检索 qrels；不下载约 16.5 GB 的 BM25/mined 训练负例和模型产物。原始 Dev 整体只作已曝光校准，Train 是 GateA/Blind 候选宇宙。
2. **Lo/DRUID `standard`**：作为英文现象/构件复现；`title/prompt` 只作配对敏感性分析。
3. **DuRetrieval 完整 pinned compact 实体**：独立保留 100,001 条 corpus、2,000 个 Query 与 9,839 条 qrel，任何 Cmedqa 重合均不扣行；用于预先声明的辅助稳健性分析，不进入当前主 Gate 分母，也不提供备用通过路径。
4. **本地 ID/provenance、通过正文验证的 corpus、索引与 LTR-v3**：作为候选生成与强基线工程资产，但必须在 P4-00/contract-lock 后重放。`990126/990127` 不复用正文。

### 6.2 已确认的数据替换与域角色边界

三主数据集中许可不明的 MedicalRetrieval 已由上游 `cMedQA2@85feb927…` 正式替换，依据是：

- 保留中文以及条件、数字、否定、时效与适用范围密集的功能角色；
- 上游有明确的 question/answer ID、Train triplet 与 Dev/Test `0/1` candidate label；
- 有可存档的 GPL-3.0 文件与 non-commercial research 声明；
- 可直接使用上游原始文本，避免 C-MTEB 紧凑版中 90,328 条 DuRetrieval 精确匹配（含 2,086 条两源共同文本）和未文档化文本变换。

研究负责人已确认项目属于非商业科研，并采用“本地研究使用，论文/复现制品只发布上游 commit、ID、hash、派生标签与 loader，不重分发全文”的保守治理。该决定在科研协议 v15 固定并由 v18 保留。cMedQA2 的医学域只是一个预注册分层属性；三套主数据使用同一事实等价/冲突/unknown schema、同一 estimand 和同一 Gate，不设医学专门终点。DuRetrieval 以完整 pinned compact 实体独立保留为辅助稳健性数据；当前主 Gate 分母不变。第一层 split/exclusion manifest 已生成，P3-02 仍须完成扩展 family 零交叉、构造率与功效分析，不能把“已选数据集”误写为“已封存样本”。

### 6.3 原 MedicalRetrieval 的后续使用边界

MedicalRetrieval 不再进入当前研究 ID 的确认性主分母。只有同时满足下列条件时，才可在另行版本化、预注册且不替换当前 cMedQA2 Gate 路径的扩展研究中使用：

- 数据许可证或维护者授权有可存档证据；
- 使用已恢复的 C-MTEB 100,999 前缀规则只作低成本先导，或在获授权后改用原始 960,526 corpus；
- pinned 文件的行数、schema、唯一键与 SHA-256 完整；
- 未标 passage 保持 unjudged，并完成聚焦 false-negative 审计；
- 医疗事实核验有合格的证据定位与复核规则。

当前替换已经在查看 Gate A 结果前完成。以后即使上述条件得到解决，也只能新增为明确标记的外部增强，不能因当前数据结果不利而把 MedicalRetrieval 换回必要单元或提供备用 Gate 路径。

### 6.4 明确排除

- C-MTEB T2 紧凑正例池单独作为完整检索 corpus；
- C-MTEB Cmedqa 的 DuRetrieval 混合 corpus 作为权威医疗正文或确认性候选总体；
- SQLite `990126/990127` 的乱码正文进入任何语义计算；
- DRUID 的 `title/prompt` 变体作为独立样本；
- DRUID 进入三数据集 C1 分母或 C3/Gate B；
- 历史 Blind v4/v5、历史聚合指标和缺行级证据的 golden 进入确认性分析；
- 公开 qrels 未出现的 pair 自动变成负例；
- 仅凭近重复、同文档、同模板或高相似判定事实冲突。

## 7. 最小人工标注包与成本下界

人工标注只在自动筛选后发生，按三阶段控制成本。

### 7.1 P2 规则校准包

最低 12 个桌面案例：

- 版本/时间、数字、否定、适用条件四类冲突各 2 个；
- 等价证据、普通错误、疑似 false negative、错误共识各至少 1 个。

全部双人独立标注并仲裁，共至少 24 次初始判断。任何案例不能唯一落入 schema 时，先修手册，不扩大样本。

### 7.2 P3 构造率先导包

建议在每个拟进入 Gate A 主分母的数据集先抽 30 个 Query family。每个 Query 只提交自动流程筛出的：

- 1 个已核验目标参照；
- 最多 8 个自然高相似/疑似漏标候选；
- 4 个自动生成或发现的等价候选；
- 四类单原子冲突各 1 个。

即每个 Query 最多 17 个候选、每数据集最多 510 个候选。若先导使用 3 个主数据集，单审上限为 1,530 个候选；最高相似项、全部等价项、全部冲突项、分歧项和 unresolved 项双审。该包只估计自然/合成构造率、标签一致性和功效参数，不进入 Gate A。

先导的停止规则：

- 某数据集不能形成目标组唯一、关系单一且相似度有共同支持的 matched chain；
- unresolved 比例过高，导致 C1 必要单元按预定功效不可估计；
- 专业核验成本超出团队可承受范围；
- 许可/provenance 仍未解决。

### 7.3 Gate A 确认性标注下界

Gate A 固定 `n=20` 的等价链与冲突链，因此每个有效 Query 至少需要：

- 20 个已核验等价压力候选；
- 20 个已核验事实冲突压力候选；
- 1 个或多个冻结前已核验的 Clean 目标参照。

若最低起点为每数据集 100 个有效 Query，则仅压力候选就是每数据集 4,000 个、三个主数据集 12,000 个内容核验；功效分析可能要求更多。自动生成、规则筛选和模型预标注可以减少送审候选池，但不能减少这 40 个最终确认性候选的内容核验。双审比例按协议集中在最高相似、全部等价、全部冲突、模型分歧和疑似漏标项，而不是重标整套 corpus。

## 8. P2-01 构念与 schema 冻结结果

当前四值 `relevant_gold / relevant_equivalent / verified_incorrect_distractor / unresolved_possible_false_negative` 把三个不同问题压在同一字段：

1. passage 是否相关；
2. passage 与目标事实是等价、冲突还是普通错误；
3. 方法从 `method_view` 能否判断正确成员。

这会使普通错误候选误入 factual-conflict 处理组，也会把两种 unknown 混淆：

- **真值未知**：标注证据不足，必须排除确认性分析；
- **方法不可裁决**：评价侧知道真值，但 `method_view` 不足以选择正确成员；它是 C2 的有效边界样本，方法应保持 LTR-v3 顺序。

已经冻结下列正交 schema：

```text
relevance_status:
  relevant_gold
  relevant_equivalent
  verified_incorrect_distractor
  unresolved_possible_false_negative

target_relation:
  equivalent
  factual_conflict
  other_incorrect
  unresolved

adjudicability:
  not_applicable
  detectable_only
  conditionally_adjudicable
  unidentifiable

candidate_pair_relation:
  same_fact
  factual_conflict
  insufficient_context
  unresolved
```

其中 `candidate_pair_relation` 只服务 Top-M 成对代理效度；候选级 `LocalConflictRisk` 才是 C2 检测主任务。原始 qrel 永不覆盖，人工层另存 `adjudicated_status`、`evidence_locator`、`rationale`、`reviewer_id`、`confidence`、`adjudication_status` 与手册版本。

该 schema 已进入[科研协议 v19](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-research.md)和[标注手册 v1（历史版本）](https://github.com/ql-link/LinkRag-Eval/blob/6adc4e247e116abf51870d1ac45fe6b90c8eb88f/docs/plans/robust-fusion-annotation-handbook.md)。P2-01 仍不标记完成：两个非 BGE 编码器的身份与确定性资格、Qwen/Jina 两个 Reranker 家族选择已经通过，但 Dev 长短文本分层人工效度、标准化/分带/共同支持实值和正式参照集合尚未冻结。

## 9. 相似度 manifest：已冻结字段，未填实值

实验相似度仍是候选与目标等价组 Clean 正确参照集合的最大余弦相似度：

\[
S_{qg}(c)=\max_{a\in A_{qg}}\cos(E(c),E(a)).
\]

manifest 至少必须固定：

- dataset、cohort 与官方 revision；
- encoder ID、精确 revision、权重 hash；
- tokenizer、输入前缀、文本规范化、截断长度；
- pooling、归一化、dtype/数值精度与实现版本；
- 每个 `A_qg` 的成员、source record ID、content hash；
- 向量文件 hash 与数据集内标准化统计；
- 低/高/模糊带、共同支持规则及敏感性边界的 Dev 时间戳。

现有 Alt Embedding 是 `BAAI/bge-m3 + 1024 dim` 的历史 sidecar，只能解释旧资产，禁止进入当前研究。[相似度 manifest v4（历史版本）](https://github.com/ql-link/LinkRag-Eval/blob/6adc4e247e116abf51870d1ac45fe6b90c8eb88f/docs/plans/robust-fusion-similarity-manifest.md)已经冻结测量对象、字段和 Gate A 拒绝条件，并在不读取研究数据时预选 `multilingual-e5-base@d1287505…` 为主编码器、multilingual DistilUSE `@bfe45d07…` 为独立审计编码器。v2 资格制品已核验精确 revision/许可/权重与 tokenizer 摘要、输入规则、维度、范数和正逆序逐值重放；这只关闭模型身份和确定性。Reranker 独立性、长度分层的人机效度、均值/标准差、分带、共同支持、覆盖阈值和参照集合仍须在 Dev 校准并封存，不能在 Gate A 结果之后补写。

## 10. 下一步与解锁条件

1. 保持全部 pinned 实体只读；不再为同一数据集追加浮动 `main` 版本。
2. 保持已生成的 P3-02 第一层资格制品：T2 原始 Dev 整体 calibration/exposed-only，GateA/Blind 从原始 Train 候选宇宙再分；1,302 项排除制品继续作审计证据。下一步补齐 document/version/counterfactual-template family 零交叉并生成最终候选资格清单。
3. cMedQA2 替换决定已经完成；四类 C-MTEB Cmedqa 来源 crosswalk 已生成但只作 provenance/曝光审计，2,536 条 unresolved 不再细分或处理。DuRetrieval 的完整 pinned compact 三实体独立保留为辅助稳健性数据，不与 Cmedqa 合并，也不临时进入主 Gate。已生成的 ID/hash-only manifest 固定 Dev-exposed、跨 split Query-family 全排除、Train-GateA-eligible 与 Test-GateB-eligible 的资格上界；它不替代后续 family 检查、构造率和功效分母。不使用许可不明的 MedicalRetrieval 或 C-MTEB Cmedqa 混合 corpus 填充必要单元。
4. 对拟复用的本地非 T2 corpus 运行 content/hash 与 exposure-family 对齐；`990126/990127` 只保留 ID/provenance 价值，正文回到 pinned 官方文件；不把 `993101/993103` 两个 Query 条件化子池用于正式 T2 候选生成。
5. `ROBUST-FUSION-P2-CALIBRATION-2026-08-28-v1` 已从 pinned T2/DRUID 生成 12 个 Dev 桌面案例；下一步由两名标注员独立完成空白表并仲裁。Medical 与 GateA/Blind family 均未进入该包。
6. 校准通过后，再执行每数据集 30 Query family 的构造率先导；只有先导和功效分析支持时才生成正式 Gate A 标注包。
7. Internal Stress v6 的三分空骨架和 intake 已建立；下一步仅摄取新的真实 Query、正确证据与通过正文/授权复核的文档，再完成 family 零重合、双审和功效分母。历史 Blind 不得重命名填充。
8. P4-00/contract-lock、P2/P3 数据资格和 P5 Dev 参数全部封存后，才允许进入 Gate A。

P3-01 已完成；T2 残余曝光已由 split-level 规则关闭第一层风险，cMedQA2 已正式替换 MedicalRetrieval，DuRetrieval 已按完整 pinned compact 三实体独立保留，C-MTEB Cmedqa 已完成可复现来源剥离且 2,536 条未解析记录不再处理。P3-04 只完成正式骨架，未完成人口。P3-02 的第一层 split/Query-family 资格制品已生成，仍缺扩展 family 零交叉、构造率、功效与最终分母封存；在这些条件完成前，P2-01、P3-02 与 P3-04 均不得标记完成，Gate A 状态保持“未运行”。
