# 鲁棒融合研究：工程实施协议

> 文档定位：本文件负责把[科研协议](robust-fusion-research.md)转化为可运行、可重放、无标签泄漏的实验系统；它不定义研究问题，也不判定论文结论。
> 工程记录：`ROBUST-FUSION-ENGINEERING-2026-08-29-v10`。
> 当前状态：真实 Python 3.11 环境与评测资产可用；Eval 薄适配已迁移到当前 LinkRag 契约并通过本地与 SSH 隧道真实栈检查，在线 Dense 重放的冻结数值容差与正式 v2 三路 preflight 已在 Gate A 前关闭，但 clean contract lock 与远端绿色 CI 尚未完成，研究专用候选快照和离线实验器尚未实现。
> 项目级状态：[CURRENT_STATUS](../CURRENT_STATUS.md)是 LinkRag-Eval 全项目进度的唯一入口；本文件只维护本研究专属工程契约。
> 配套入口：[科研协议](robust-fusion-research.md)、[研究推进清单](robust-fusion-todo.md)、[资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)。
> 最近更新：2026-08-29。

## 0. 一页摘要

本研究的工程目标不是另外搭建一套 RAG，而是利用 LinkRag 与 LinkRag-Eval 已有能力，增加两个研究仪器：

1. **Candidate Snapshot Generator**：从冻结语料、Query/qrels 和三路检索结果生成不可变候选快照；
2. **Offline Fusion and Reranking Experimenter**：只读取快照，把完全相同的候选池交给所有方法并生成可审计结果。

工程系统必须保证四件事：

- 不写生产数据库或生产 collection；
- 方法侧看不到 qrels、Gold、冲突类型等评价真值；
- 同一条件下所有方法接收逐 ID 相同的候选池；
- 任意结果都能追溯到数据、模型、代码、配置和内容摘要。

> **概念解释｜研究仪器**：这里不是指物理设备，而是产生候选、执行排序和计算指标的软件。仪器测试只能证明结果可重放，不能证明研究假设成立。

## 1. 与科研协议的职责边界

| 内容 | 唯一维护位置 | 另一份文档如何使用 |
| --- | --- | --- |
| 题目、RQ、假设、构念和结论边界 | [科研协议](robust-fusion-research.md) | 工程侧按版本读取，不自行修改 |
| 数据角色、Dev/GateA/Blind 用途 | [科研协议](robust-fusion-research.md) | 工程侧实现物理隔离和访问限制 |
| 相似度、关系标签、指标和 Gate 规则 | [科研协议](robust-fusion-research.md) | 工程侧实现为配置、校验和分析 |
| 环境、存储、接口、快照 schema 和重放流程 | 本工程协议 | 科研侧只引用能力与限制 |
| 全项目最新工程进度 | [CURRENT_STATUS](../CURRENT_STATUS.md) | 本文件不复制全项目状态 |
| 本研究当前任务和完成证据 | [研究推进清单](robust-fusion-todo.md) | 两份协议共同引用 |

同步规则：

1. 科学定义变化时，先更新科研协议的研究记录，再更新本文件受影响的字段、校验和任务；
2. 环境、接口或资产变化时，先更新 `CURRENT_STATUS.md` 或正式报告，再更新本文件；
3. 只有工程实现发生变化而科学含义不变时，不修改科研协议；
4. 两份协议不得分别维护同一个阈值、样本量或结果数字；科研阈值以科研协议为准，资产数字以正式报告为准；
5. 每个候选快照必须记录所依赖的科研协议版本和工程协议版本。

## 2. 当前工程基础

截至 2026-08-28，真实环境已经解除“无法取得真实三路证据”的工程阻塞。

| 资产 | 已核验状态 | 研究用途 | 使用限制 |
| --- | ---: | --- | --- |
| 主 SQLite | 22 个目录项、49,774 个 Chunk | ID/provenance、文档关系、历史运行元数据；逐集验证后的正文 | `eval_query`、`eval_qrel` 均为 0；`990126/990127` 各 800 条正文与 pinned 官方文本 0 条完全一致且可见乱码，只复用 ID/provenance |
| SQLite FTS5 BM25 | 31,072 条、11 个数据集 | 真实 BM25 检索 | 仅覆盖主库子集 |
| Alt Embedding | 20,772 条、9 个数据集、1,024 维历史 BGE-M3 sidecar | 历史候选生成资产追溯 | BGE-M3 已淘汰；不得进入 Gate A route、实验相似度或候选筛选 |
| 当前 eval Qdrant | 44,773 点、状态 green | Dense/Sparse 检索 | 是主 SQLite 的严格子集 |
| 历史 eval collections | 存在当前主库交集和历史独有记录 | 追溯历史运行 | 不得与当前 collection 拼成确认性快照 |
| `candidate_difference_v3` | 已有 38 维线上特征模型包 | LTR-v3 强基线 | 不把已有特征重新包装为新方法 |

资产计数和逐数据集覆盖的权威来源是[资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)。本表只作当前实施入口；资产改变时更新报告，而不是直接覆盖历史数字。

这些资产不包含本研究所需的完整 Query/qrels，也不自动具有 Dev、GateA、Blind 身份。因此它们是工程输入，不是确认性样本。“SQLite 可读”只是存储状态，不代表正文语义已通过权威实体对账；正式 snapshot loader 必须对每个公开数据集验证 pinned ID、正文与 hash。

## 3. 环境与隔离

### 3.1 环境角色

- LinkRag 使用其 Python 3.11 环境和 `.env.development`，提供生产代码与服务口径；
- LinkRag-Eval 使用本项目 Python 3.11 环境和 `.env.eval`，执行研究数据入库、召回、快照和离线实验；
- 缺失依赖优先补入双方约定的共享开发路径，不另建一套与生产计算脱节的研究实现；
- `.env.eval` 与 `.env.development` 都不进入版本库，任何日志和 manifest 不得记录 API Key。

### 3.2 存储护栏

- 元数据、研究标签和结果只写本地 SQLite 或研究产物目录；
- Qdrant collection 名必须包含 `eval`；
- `EVAL_USER_ID` 只作为路由常量，不表示真实用户；
- 不读取或写入生产 ORM、生产 MySQL、生产 MQ 或生产对象存储；
- 历史 collection 默认只读，不清理、不迁移、不合并；
- 轨道 B 的写入目标必须是新建且带研究快照标识的 eval collection。

> **概念解释｜环境隔离**：复用生产计算代码，不等于复用生产数据存储。研究运行必须在独立配置、独立数据库和带 `eval` 前缀的 collection 中完成。

### 3.3 生产能力复用边界

本项目继续遵守仓库 `AGENTS.md` 的 adapter 白名单：只通过 Eval 薄适配层复用纯计算、Qdrant 原语和被测 Recall 接口。研究代码不得为了方便直接依赖生产 ORM、写入 pipeline 或生产配置对象。

当前召回和存储接口以实际代码、契约测试和运行快照为准，不以 README 中可能过期的“默认 RRF”或“BM25 位于 Qdrant”等描述为准。实验中：

- Dense 固定读取 `.env.eval` 的 `text-embedding-v4` 在线 API 口径；
- Learned Sparse 固定读取 `ark / doubao-embedding-vision-251215` 在线 API 口径；
- BM25 固定为 eval 自持 `sqlite_fts5`；
- BGE-M3 兼容客户端与服务器只用于解释历史资产，Gate A preflight 必须拒绝把它装配为 route 或相似度编码器；
- Fixed Weighted Fusion 是当前稳定融合基线；
- RRF 是单独实现的无监督基线；
- BM25 backend 必须写入快照，不能把 SQLite FTS5 与其他 backend 混称为同一实现；
- 轨道 B 若声称接近生产外部有效性，必须记录当时生产实际 backend。

### 3.4 当前 LinkRag 契约复验与 CI 重钉

旧 CI 只证明 LinkRag-Eval 与历史 LinkRag revision `6296990fd80181f0f7608746faf259a9aa256dc0` 的契约曾经兼容，不能证明它与本研究审计的 LinkRag revision `861f24810c3482ec0d86768a24f952b1e08ae675` 兼容。本轮已只修改 Eval 薄适配层，删除对已移除 `BucketRouter`/`bucket_router=` 的依赖，按冻结的历史路由公式解析显式 eval collection，并把 CI pin 更新为 `861f2481…`。本地非集成套件、import-lint、当前 `candidate_hits/route_hits` 契约、LTR-v3 三个固定向量和通过 SSH 隧道连接真实 Qdrant 的集成测试已通过；但工作区仍 dirty，且尚无此次版本的远端绿色 CI run，所以 P4-00 仍是“部分完成”，不能生成正式 `contract-lock.json`。

P4-00 是不依赖 P2/P3 研究样本的独立工程 preflight，可立即开始。正式候选快照冻结前，必须完成真正的 current-HEAD 契约复验与 CI 重钉：

1. 在 Python 3.11 和实际 `.env.eval` / `.env.development` 口径下运行 Eval 单元、契约及所需真实栈冒烟；
2. 验证当前 `RecallResponse.candidate_hits`、`route_hits`、路内排名、分数变换、缺路语义和截断行为；
3. 用固定小样例重放 Dense、Learned Sparse、BM25、粗融合与 LTR-v3 候选契约；
4. 只修改 Eval 薄适配层以适配现行 `QdrantIndexStore(collection_name=...)`、Retriever/Pipeline 和候选契约；不恢复已删除的生产接口；
5. 把 CI 的 LinkRag pin 更新到实际用于研究的精确 clean commit，运行单元、契约、import-lint 及所需真实栈冒烟，并保存绿色 CI run ID 与本地报告摘要；
6. 生成机器可核验的 `contract-lock.json`，记录 LinkRag/LinkRag-Eval commit 与 tree、`dirty=false`、候选契约签名、LTR 特征/模型摘要、依赖锁摘要、Python 版本、模型绑定、backend、collection 和环境配置脱敏摘要；
7. 若预检不得不在 dirty 工作区运行，必须额外记录 tracked diff hash 与 untracked 内容清单/hash，但该结果只能诊断，不能解除正式快照门禁；正式锁定必须回到可解析的 clean commit/tag。

只有薄适配层修复、CI 精确 pin、绿色 run/report 和 clean `contract-lock.json` 四者同时存在，P4-00 才能完成。它是快照冻结的工程硬前置条件，但不构成 Gate A 科研证据。

真实 route 另由 `scripts/probe_robust_fusion_route_contract.py` 拒绝错误配置。历史 v1 制品曾验证 `.env.eval` 为 Ark/`doubao-embedding-vision-251215`、`top_k=256`、SQLite FTS5，并用四条中英固定输入按正序/逆序在线重放得到逐条相同的 canonical Dense/Sparse float32 摘要；科研协议 v19 联动刷新时，Dense 的 `zh_short` 又发生一次只知 hash 不同、未保留幅度的 exact mismatch。该失败不自动重试，也不被事后改写成“已证明只是尾差”。

研究负责人随后在 Gate A、候选、qrel 和排序结果均未读取的条件下，授权一次只测量的 Dense 诊断复放。`ROBUST-FUSION-DENSE-REPLAY-DIAGNOSTIC-2026-08-29-v1` 以同四条固定无敏感文本发出正序/逆序两次请求，`max_retries=0`；本次 4×1024 个 float32 分量全部逐位一致，最大绝对差、relative L2、归一化向量差和任一单位候选的余弦分数扰动上界均为 0。重新计算余弦时出现的 `2.22e-16` 只是本地 float64 舍入，不是 API 向量漂移。制品 SHA-256 为 `3606a60aca87d41f959214c121b402a1c0ea303d228629cfac622d5648ec9081`；它不保存原文、向量、端点或密钥，不读取实际候选及研究结果。

在看到该次诊断结果前写死的数值界现正式冻结为 `ROBUST-FUSION-DENSE-REPLAY-POLICY-2026-08-29-v1`。正式 route preflight 对每条探针分别执行以下交并规则，不允许探针间平均抵消：float32 逐位一致直接通过；否则只有以下五项全部不超过上界才可记为 `WITHIN_FROZEN_NUMERIC_TOLERANCE`：

- 最大逐分量绝对差 `<= 1e-6`；
- relative L2 差 `<= 1e-5`；
- 归一化 Query 向量 L2 差 `<= 1e-5`；
- 余弦距离 `<= 1e-8`；
- 任一单位候选的余弦分数扰动数学上界 `<= 1e-5`。

任一探针、任一上界超限即失败，禁止自动重试或临时改阈值；Learned Sparse 仍要求 canonical float32 摘要 exact。正式候选生成只调用一次在线 route 并立即冻结候选 ID、逐路分数、请求/输出摘要和 tie-break，Gate A 离线运行不得再次调用在线编码服务。上述策略关闭的是“如何判定 provider-managed 数值重放”的规则空缺，不证明先前未测量 mismatch 的实际幅度，也不替代双仓 clean 和绿色 CI。

负责人随后授权正式 v2 三路 preflight，命令只执行一次且没有自动重试。`ROBUST-FUSION-ROUTE-CONTRACT-PREFLIGHT-2026-08-29-v2` 通过：Dense 四探针全部 float32 exact，`replay_acceptance=EXACT`；Ark/豆包 Sparse 四探针 canonical float32 摘要全部 exact；BM25 绑定 `sqlite_fts5`。manifest SHA-256 为 `640e3d52a2f7cfc6f991cefe4d111ae18d09ba3260626a2e927988b5cd17a38a`，不保存原文、向量、端点或密钥，且 `gate_a_executed=false`、`outcome_data_read=false`。因此在线三路重放阻塞已经关闭；P4-00 仍因双仓非 clean、缺当前版本远端绿色 CI 和正式 `contract-lock.json` 而未完成。

> **概念解释｜CI pin 与契约重钉**：CI pin 是自动测试所绑定的代码版本。生产代码更新后，旧版本测试通过不能证明新版本仍兼容；契约重钉就是在准备正式实验时重新确认并记录双方实际版本和接口行为。

> **概念解释｜Contract lock**：`contract-lock.json` 是机器可读的接口锁定单。它同时记录两边代码、候选字段语义、模型和运行环境，使“测试过当前版本”不再只是一句无法复核的文字。

## 4. 输入数据准备契约

### 4.1 公共数据

每个公共数据集在进入快照生成前必须具备：

- 数据集名称、来源地址、许可证和冻结 revision；
- 原始文件 SHA-256 与规范化后文件 SHA-256；
- corpus、Query、qrels 的记录数和唯一 ID 检查；
- Query—文档族分组和 Dev/GateA/GateB 划分清单；
- qrels 漏标审计记录；
- 一个原始 corpus record 对应一个实验 Chunk，不经 LinkRag 二次切分。

cMedQA2 的正式 loader 额外满足：

- 输入只绑定上游 commit `85feb9278c3ae552c591205cbf3e828368c91f8f` 及数据审计记录的七个文件摘要，不从 C-MTEB Cmedqa 或 SQLite `990127` 读取正文；
- 原始全文只保存在 gitignored 的本地研究数据目录；版本化复现制品只允许包含上游 commit、官方 ID、内容 hash、派生标签、split/exclusion manifest 与 loader，不复制问题或回答全文；
- Unicode NFKC、首尾空白删除和连续空白折叠后的 Query 文本作为第一层 family key；任何同时出现在两个以上游 split 的 family 全部进入 confirmatory exclusion；
- 固定输入的资格审计必须复现 Train/Dev/Test 为 100,000/4,000/4,000 个 Query、80 个跨 split family、按 split 涉及 106/35/46 个 Query、排除后 Train/Test 资格上界为 99,894/3,954，且三个 split 的正例 answer ID 两两交集为 0；任一不一致都拒绝生成快照；
- 原始 Dev 只进入 calibration/exposed-only，剩余 Train/Test 分别只是 Gate A/Gate B 的资格母池。除只读资格/hash 封存工具外，方法开发与实验运行代码在 M1 冻结前不得读取 Gate B 正文；正式抽样还要继续执行 document/version/template family 隔离和功效冻结。

DuRetrieval 的独立完整性 loader 必须同时满足：

- 只绑定 C-MTEB data revision `a1a333e290fe30b10f3f56498e3a0d911a693ced` 与 qrels revision `497b7bd1bbb25cb3757ff34d95a8be50a3de2279`，并逐文件核验数据审计中冻结的三个 SHA-256；
- 完整读取 100,001 条 corpus、2,000 个 Query 与 9,839 条唯一 qrel pair；corpus/Query ID 与原文均唯一且非空，qrel 只能取 `score=1`，所有 QID/PID 引用有效；
- 禁止按 C-MTEB Cmedqa 的文本重合、来源类别或 qrel 关联删除、合并、替换、抽样修补 DuRetrieval 记录；快照 manifest 必须记录三个实体 `rows_removed=0`；
- 当前只允许进入显式标记的辅助稳健性分析，主 Gate runner 必须拒绝把它临时并入六单元 C1 分母或 Gate B。改变角色需要绑定新的 Gate 前科研协议版本。

C-MTEB Cmedqa 只允许通过 `scripts/audit_cmedqa_corpus_provenance.py` 生成的 v2 ID/hash-only crosswalk 参与 provenance 与曝光检查。生成器必须复现 100,001 条的四类精确来源计数：`duretrieval_exact_only=88,242`、`cmedqa2_exact_only=7,137`、`both_exact=2,086`、`unresolved_neither=2,536`；3,999 个 Query 中 3,985 个精确匹配上游问题，7,321 个 qrel PID 中 7,165 个精确匹配上游回答，7,449 个 qrel 文本对中 7,262 个匹配上游 Dev 正例文本对。任一不一致都拒绝加载 crosswalk。全部 2,536 条 `unresolved_neither` 必须保持同一仅审计类别；不得按 qrel 关联生成子清单或动作，不得做归一化/模糊回配、专项标注、删除或正式语义加载。该制品不含正文，不得作为权威 cMedQA2 corpus 或未标负例来源，也不得作为裁剪 DuRetrieval 的依据。

### 4.2 内部数据

内部数据需要三个物理隔离 manifest：

- `internal-v6-dev`；
- `internal-v6-gatea`；
- `internal-v6-blind`。

划分单位是 Query、文档族、文档版本和反事实模板组成的组，而不是单个 Chunk。Blind 目录在 M1 冻结前不得被实验代码扫描、计数或读取正文。

内部文档只允许一次性确定性切分，并保存 parser、chunker、参数、代码 SHA、原文位置和 Chunk 内容摘要。

唯一内部数据协议为[Internal Stress v6 数据协议](robust-fusion-internal-stress-v6.md)。`scripts/initialize_robust_fusion_internal_v6.py` 已建立本地 gitignored 三分目录、独立 cohort manifest、GateA/Blind 方法访问锁、source/exposure 台账、四张最小摄取模板和全包摘要。当前 root 状态必须保持 `FORMALLY_ESTABLISHED_AWAITING_NEW_REAL_QUERY_INTAKE`、`gate_eligibility=NOT_ELIGIBLE`，因为分享包、旧 eval MySQL 与服务器均无 Query/qrel 行；任何 runner 都不得把“目录存在”解释为“人口已冻结”。

### 4.3 干扰构造

自然候选和合成反事实分开保存。每个合成项至少包含：

- `parent_chunk_id`；
- 变更前后文本片段；
- 单一原子变换类型；
- 错误理由；
- 复核状态；
- 重算后的 Dense、Sparse、BM25 证据。

严禁复制父 Chunk 的检索分数、排名或 retrieved flag。

## 5. Candidate Snapshot Generator

### 5.1 输入与输出

输入：

- 冻结 corpus、Query、qrels 和等价组；
- 三路 Retriever 配置；
- 科研协议冻结的候选深度、相似度 manifest 和压力构造规则；
- 数据、模型、代码、配置和随机种子指纹。

输出是只读、版本化的候选快照。逻辑上至少包含：

| 字段组 | 必要内容 |
| --- | --- |
| Query | dataset、revision、split、query_id、正文、内容摘要 |
| Chunk | chunk_id、原始 corpus ID、doc_id、document family/version、正文、内容摘要 |
| 三路证据 | retrieved flag、raw score、original rank、observed/recomputed |
| 评价真值 | relevance、relation、equivalence group、target group、冲突类型、置信度 |
| 压力构造 | Clean/Stress、pool role、relation condition、similarity band、natural/synthetic origin、dataset origin quota/version、pressure pool、replacement chain、父项、原子变换、剂量 |
| 相似度 | 编码器、tokenizer、输入模板、截断、pooling、归一化、向量摘要 |
| 指纹 | 科研/工程协议版本、clean LinkRag/LinkRag-Eval commit 与 tree、`contract-lock.json` 摘要、依赖与 Python 摘要、数据 revision、模型版本、backend/collection、配置摘要、随机种子、内容 SHA |

物理存储格式在 P4-01 审计后选择；无论使用 SQLite、Parquet 或其他格式，上述逻辑字段和不可变性都必须满足。

### 5.2 两个数据视图

快照必须生成两个不可混用的投影视图：

| 视图 | 可见字段 | 消费者 |
| --- | --- | --- |
| `method_view` | Query/Chunk 正文、允许的文档元数据、三路分数/排名/命中、确定性推理特征 | B1—B10、D1—D3、A0、M1 |
| `evaluation_view` | qrels、Gold、等价/冲突标签、目标组、相似分带、natural/synthetic origin 与配额版本、pool role、压力链、父项和注入剂量 | 构造器、指标和审计器 |

离线实验器不得把两个视图重新 join 后交给方法。删除、置换或脱敏 `evaluation_view` 后，方法输出必须逐值不变。

> **概念解释｜数据视图**：同一快照按用途暴露不同字段。方法只看部署时能获得的信息，评价程序才看人工真值，从结构上减少标签泄漏。

### 5.3 不可变与重放

- 快照一旦封存不得覆盖；正文、qrels、模型或配置改变都生成新 `snapshot_id`；
- 快照根摘要由所有逻辑文件的内容摘要确定；
- 重放时先验证摘要和 schema version，再运行方法；
- 同一快照、方法包和随机种子重复运行，确定性输出必须完全一致；
- 快照不得依赖在线 Qdrant 才能被离线实验器读取。

## 6. 两条实验轨道的工程实现

### 6.1 轨道 A：固定候选池

实现顺序：

1. 三路深召回形成候选超集；
2. 校验目标等价组已自然进入超集；
3. 建立固定大小 Clean 池；
4. 按科研协议匹配普通负例并建立嵌套替换链；
5. 生成各剂量 Stress 池；
6. 对候选 ID、组级 gain、IDCG、池大小和随机种子执行配对校验；
7. 写入不可变快照；
8. 之后所有排序运行离线完成。

任何一项配对校验失败，该 Query—条件不得进入主分析。

### 6.2 轨道 B：索引级干预

轨道 B 使用独立 eval collection：

1. 复制冻结基础语料到新研究数据版本；
2. 加入经过复核的干扰 Chunk；
3. 用正式计算路径重算 Dense、Sparse 和 BM25；
4. 重新运行三路召回；
5. 将召回结果固化为另一个候选快照；
6. 报告 Gold 召回变化和排序变化，不与轨道 A 混写。

轨道 B 不得向现有共享 collection 增量写入后再声称是冻结实验。

## 7. Offline Fusion and Reranking Experimenter

离线实验器只接受 `snapshot_id` 和冻结方法配置，禁止访问在线 Retriever。它至少负责：

- 运行 B1—B10、D1—D3、A0 和 M1；
- 为每个 Query 输出完整排序、候选分数和方法状态；
- 记录 Reranker 模型 ID、revision、截断、批处理和推理配置；
- 计算 EG 指标、官方指标、Clean/Stress 成对差值、翻转率和 nAUDC；
- 按科研协议固定的 Query→family→数据集宏平均重算 C2、nAUDC 和 Clean 估计量，并在每个 bootstrap 重采样中复用同一 family 索引；
- 只将冻结的高相似 verified-conflict 与 origin 配额压力链送入 Gate B 主终点，其他分层输出必须标记为诊断；
- 对 LTR-v3/D3/A0 重算 5/10/20/50 剂量中固定不变的成对共同 Clean 正确风险集和最坏翻转率差；覆盖率严格按“family 内共同正确 Query 比例→数据集内 family 等权平均”计算，有效 family 只计至少含一条共同正确 Query 者；风险集为空或低于冻结覆盖门槛时拒绝产生“通过”结果；
- 输出 Query 级长表，保留失败和降级状态；
- 执行 `evaluation_view` 置换不变性检查；
- 记录运行指纹、耗时、资源、错误和审计日志。

方法插件的最小逻辑接口为：

```text
rank(method_view, method_config) -> ordered candidates + scores + status
```

指标接口为：

```text
evaluate(ranking, evaluation_view, metric_config) -> query-level metrics
```

这样方法执行与评价真值在接口层分离。

## 8. M1 与基线的实现约束

- LTR-v3 必须直接加载冻结模型包和特征签名；
- D1—D3、A0 与 M1 使用相同学习器、训练数据、新增特征数、调参次数和资源预算；
- A0 只使用表面特征，不含局部密度；其模板相似只能从 `method_view` 中的 Query/Chunk 文本确定性计算，不得读取 `evaluation_view` 的 transformation-template identity、父项或构造链；
- M1 只新增科研协议定义的局部拥挤、局部冲突和六个分路 score/rank margin；
- Top-M 相似矩阵按 Query 计算并释放，不建立持久化候选图；
- Query 未提供正确值的槽只能输出 conflict/unknown，不能调用人工答案；
- 相似度、冲突阈值、归一化和缺失编码由冻结配置注入，不在代码中散落硬编码；
- Gate A 之前不得实现或训练 D1—D3、A0、M1。

## 9. 运行产物与目录约定

研究产物建议统一置于 gitignored 的 `runs/robust_fusion/`。逻辑目录为：

```text
runs/robust_fusion/
├── datasets/       # 冻结数据 manifest 与摘要
├── snapshots/      # 候选快照，只读版本
├── methods/        # 冻结方法配置引用，不复制秘密
├── runs/           # 完整排序和 Query 级结果
├── audits/         # 泄漏、配对、覆盖、false-negative 审计
└── reports/        # 由运行产物生成的研究报告
```

具体文件格式和命名在 P4-01 冻结。任何产物不得包含 API Key、生产用户信息或未脱敏的敏感内容。

## 10. 验证与验收

### 10.1 单元与契约检查

- 快照 schema、必填字段和枚举合法；
- `method_view` 不含 evaluator-only 字段；
- 候选池大小、ID、目标组、gain 和 IDCG 配对一致；
- EG 指标在手工小样例上与定义一致；
- nAUDC 在缺失剂量和不共同 cohort 时拒绝计算；
- pooled 分析在修改数据集权重、改用 micro 聚合、混入非主 Stress population 或选择性缺失方法输出时拒绝 Gate 模式；
- Top1 安全在任一基线×数据集共同风险集为空、低于 `F_min,flip/rho_min,flip` 或缺失任一主剂量时输出 `Inconclusive`，不得跳过该格；
- 路由缺失、模型失败和截断不会静默变成空结果；
- 本地确定性计算必须逐位一致；provider-managed Dense 按第 3.4 节的逐探针 `exact OR 五项冻结数值容差交集` 判定，Learned Sparse 仍须 exact，任何超界均拒绝且不自动重试。

### 10.2 真实栈冒烟

在 `.env.eval` 下逐数据集验证：

- 主 SQLite 正文可读，且拟复用的公开正文与 pinned 权威文件的 ID/content hash 相等；`990126/990127` 必须从官方文件重建，不得继承历史向量或 token；
- 目标数据集的 BM25、Dense、Sparse 实际可检索；
- 当前 backend、collection、模型和覆盖数写入 manifest；
- Qdrant 写入目标带 `eval` 前缀；
- 运行不访问生产数据库；
- 三路结果能够固化后离线重放。

### 10.3 科研仪器验收

工程进入 Gate A 前必须满足：

1. 第 3.4 节 current-HEAD 契约复验与 CI 重钉完成，`contract-lock.json` 指向 clean 双仓 commit，且保存绿色 CI run ID/report；
2. 所有方法读取同一候选池摘要；
3. 方法输出对 `evaluation_view` 置换不变；
4. 重复运行结果一致；
5. 指标小样例通过人工复算；
6. 失败和排除 Query 有完整原因；
7. 快照不依赖在线服务即可重放；
8. 运行报告能够回溯全部版本、backend、模型绑定和内容摘要；
9. Gate A root manifest 能解析所有协议、代码、数据、快照与配置摘要；运行清单能同时解析 root hash 和外部时间戳 receipt sidecar。

通过这些条件只表示研究仪器可用，不等于 Gate A = Go。

## 11. 实施顺序

| 顺序 | 工程任务 | 前置条件 | 产出 |
| ---: | --- | --- | --- |
| 1 | 完成 P4-00 current-HEAD 契约复验与 CI 重钉 | Python 3.11 与真实环境可用；不依赖 P2/P3 样本 | Eval 薄适配、精确 CI pin、绿色 run/report、`contract-lock.json` |
| 2 | 审计现有候选缓存和运行产物 | P2-01 的字段定义可用 | 字段缺口表 |
| 3 | 冻结公共数据与内部三分输入 | 标注规则可执行 | 数据 manifest 与内容摘要 |
| 4 | 实现最小快照生成器 | 数据与三路接口可用 | 可重放快照 |
| 5 | 实现视图隔离和 EG 指标 | 快照 schema 冻结 | 指标校准报告 |
| 6 | 实现离线实验器和现有基线 | 方法接口冻结 | 完整排序与运行指纹 |
| 7 | 运行校准先导 | 仪器验收通过 | 方差、成本和可构造率；工程侧不决定效应门槛或 Gate 规则 |
| 8 | 生成并资格复核 Gate A 快照 | 科研构造规则、样本分母和仪器已冻结 | 只读快照与逐项内容摘要；不运行确认性排序 |
| 9 | 冻结 root manifest 与代码 | 第 8 项完成 | commit/tag、root SHA-256；正式产物使用 clean 双仓状态 |
| 10 | 获取外部时间戳并解锁 | root hash 已冻结 | 引用 root hash 的 receipt sidecar 与 Gate A 运行清单 |
| 11 | Gate A = Go 后实现 D1—D3/A0/M1 | 科研门禁通过；相关实际效应界已在观察方法差值前冻结 | Gate B 方法包 |

当前可以直接开始第 1—2 项；第 3 项仍依赖 P2 构念和标注规则。工程实现不得越过科研准入条件。

## 12. 已知风险与处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| 各资产覆盖范围不同 | 某数据集缺少一条检索路 | 逐数据集做实际存在性检查，不读历史 flag 推断 |
| 公共数据缺少本地实体 | 无法生成正式 Query/qrels | 下载、冻结 revision 并重新审计 |
| SQLite 正文编码/内容与官方实体不一致 | 基于乱码生成 embedding、BM25 或候选，使语义快照失效 | 逐 ID/content hash 验证；未通过时从 pinned 官方文件重建，不修补或继承旧向量 |
| 紧凑派生 corpus 混入其他数据集 | 数据集域角色和负例分布被误述，或反向破坏 DuRetrieval 完整性 | 正式 loader 绑定上游 provenance 与逐实体对账；DuRetrieval 三实体完整读取且 `rows_removed=0`；C-MTEB Cmedqa 只读四类 ID/hash crosswalk，不进入权威 cMedQA2 快照；`both_exact` 不强制归因，全部 `unresolved_neither` 统一留在仅审计类且不触发处理 |
| 把 Internal v6 空骨架当作已封存 cohort | Gate A/B 运行在无真实 Query/真值或事后填充数据上 | root manifest 明示 `NOT_ELIGIBLE`；runner 要求非空、双审、family 零交集、功效分母与 seal 全部通过才解锁 |
| cMedQA2 全文误入版本库或公开复现包 | 违反已确认的非商业本地使用治理并扩大数据暴露 | 原始 zip/正文只留在 gitignored 数据目录；版本化产物仅存 commit、ID、hash、派生标签、排除表和 loader；CI 检查禁止正文文件进入 seal |
| 历史 collection 更“完整” | 容易误拼不同模型和版本 | 单快照只绑定一个冻结 collection/backend |
| 历史 BGE-M3/Alt Embedding 被误接回正式研究 | route 口径错误，相似度不可复算 | Gate A preflight 对 BGE provider/model 直接拒绝；历史 sidecar 只读追溯，不复用、不重算 |
| Reranker API 或模型漂移 | 结果不可重复 | 冻结模型 ID/revision/参数并缓存原始分数 |
| LinkRag 当前 HEAD 与 Eval 旧 CI pin 漂移 | 现有 `BucketRouter` 适配无法代表当前生产候选契约 | 按第 3.4 节修 Eval 薄适配、更新精确 CI pin，并以 clean `contract-lock.json` 和绿色 run/report 验收 |
| 双仓 SHA 对应 dirty 工作区 | 相同 SHA 可能运行不同的未提交内容 | 预检记录 diff/untracked hash；正式快照只接受 `dirty=false` 的 commit/tag |
| Seal、root hash 与时间戳互相引用 | 产物无法形成唯一无环指纹 | 先冻结 root manifest，再时间戳 root hash；receipt 只作不进入 root hash 的追加 sidecar |
| evaluator 字段泄漏 | 方法结果虚高 | 物理视图隔离和置换不变性测试 |
| 在线服务波动 | 部分 Query 缺路、超时或数值轻微变化 | route preflight 按第 3.4 节冻结容差逐探针判定且不自动重试；正式快照生成阶段显式失败或一次性固化，离线阶段不调用在线服务 |
| 计算预算超限 | 无法完成全矩阵 | 按科研协议的缩减顺序执行，不降低核心证据标准 |

## 13. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-08-29 | v10 | 在一次获授权、无自动重试且 outcome-blind 的 Dense 诊断复放中，四条探针全部 float32 exact；保留 v19 未测量 mismatch 的历史边界，并在结果前写死的五项上界基础上冻结 `exact OR 数值容差交集` 重放策略。随后获授权的正式 v2 三路 preflight 一次通过，Dense/Sparse 均走 exact；P4-00 仅继续受 clean 双仓、远端绿色 CI 与正式 lock 阻塞 |
| 2026-08-28 | v9 | 同步科研协议 v18；冻结真实三路为 `text-embedding-v4`、Ark/豆包 Learned Sparse、SQLite FTS5；BGE-M3 退出当前研究；记录 Eval 薄适配、CI pin、本地全测、LTR 固定向量和 SSH 隧道真实栈已通过，但 clean lock/远端绿色 CI 仍未完成 |
| 2026-08-28 | v8 | 同步科研协议 v17；把 pinned C-MTEB DuRetrieval 的 100,001/2,000/9,839 完整性、零重合扣除和辅助分析角色写入 loader 拒绝条件；C-MTEB Cmedqa 的 2,536 条 `unresolved_neither` 固定为不分 qrel 子类、不回配、不专项标注、不删除、不作正式语义输入 |
| 2026-08-28 | v1 | 从原研究总文档拆出环境、资产、快照、离线实验器、隔离、重放和验收要求；建立科研/工程双文档维护边界 |
| 2026-08-28 | v2 | 将当前 LinkRag 契约重钉、双仓/环境指纹和预注册时间戳解析列为正式快照与 Gate A 前的工程硬前置条件 |
| 2026-08-28 | v3 | 将已知 `BucketRouter` 漂移写成阻塞事实；要求薄适配、精确 CI pin、绿色 run 和 clean contract lock；补入 A0；消除快照、root manifest 与外部时间戳的顺序环 |
| 2026-08-28 | v4 | 同步科研协议 v12 的高相似冲突主 Stress population、origin 配额、确证性 macro-pooled estimand、Top1 最坏剂量与最低共同风险集拒绝规则 |
| 2026-08-28 | v5 | 将公开正文的 pinned ID/content-hash 对账升为 snapshot loader 硬契约；排除 SQLite `990126/990127` 乱码正文/历史向量与 C-MTEB Cmedqa 混合 corpus 进入正式语义快照 |
| 2026-08-28 | v6 | 同步科研协议 v15 的 cMedQA2 正式替换决定；冻结上游 commit、本地全文治理、跨 split Query-family 排除及 Dev/Train/Test 资格母池的 loader 契约 |
| 2026-08-28 | v7 | 同步科研协议 v16；加入 C-MTEB Cmedqa 四类逐 ID/hash provenance peel 契约，并正式建立 Internal Stress v6 三分目录、访问锁、摄取 schema 与 `NOT_ELIGIBLE` 空人口门禁 |
