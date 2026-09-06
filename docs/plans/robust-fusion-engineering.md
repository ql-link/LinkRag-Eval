# 鲁棒融合研究：工程实施协议

> 文档定位：本文件负责把[科研协议](robust-fusion-research.md)转化为可运行、可重放、无标签泄漏的实验系统；它不定义研究问题，也不判定论文结论。
> 工程记录：`ROBUST-FUSION-ENGINEERING-2026-08-30-v23`。
> 当前状态：真实 Python 3.11 环境与评测资产可用；Eval 薄适配已迁移到当前 LinkRag 契约并通过本地与 SSH 隧道真实栈检查，历史正式 v2 三路 preflight 已关闭模型/schema/连通性证据。当前 provider-managed Dense/Sparse 不设数值重放门槛，改为单次生成、结构校验和哈希封存。Internal v6 的 30-family Dev 生成、不可覆盖恢复链、A/B 双审提交锁、机械校验和主持人裁定已落地，人工接纳 28/30。Dev-only 三路证据的 v2/v3 失败与 v4 完整性拒收均保留，修复后的独立 v5 已在真实 Dense、Learned Sparse、BM25、SQLite 与 Qdrant 上完成并独立核验。P2-01 v1 人工效度 PASS、共同支持 `INCONCLUSIVE` 的全部制品保持只读；唯一一次 72-family Dev 共同支持补充已完成四提交先锁后验和零仲裁单次终审。combined 共同支持 96%/99% PASS，但 supplement-only/combined 人工效度均为 `INCONCLUSIVE`，故 terminal `INCONCLUSIVE`、无正式数值冻结、P2/Gate 未完成且无第三轮。C2 边界补充包仍为空白规划。R2 当前等待一名新研究员完成 7 行关系与 96 行相似度仲裁，并已建立统一的 `human_tasks/<task-id>/` 浅入口；后续所有人工复核、仲裁、签署和独立评审均须在交付前通过同一入口门禁。clean contract lock、远端绿色 CI、正式研究候选快照和离线实验器仍未完成。
> 项目级状态：[CURRENT_STATUS](../CURRENT_STATUS.md)是 LinkRag-Eval 全项目进度的唯一入口；本文件只维护本研究专属工程契约。
> 配套入口：[科研协议](robust-fusion-research.md)、[研究推进清单](robust-fusion-todo.md)、[资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)。
> 最近更新：2026-08-30。

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

真实 route 另由 `scripts/probe_robust_fusion_route_contract.py` 拒绝错误配置。历史 v1/v2 探针与 Dense 诊断制品原样保留：它们曾记录一次幅度未知的 Dense exact mismatch、一次四探针 exact 诊断，以及正式 v2 中 Dense/Sparse exact、BM25=`sqlite_fts5` 的结果。正式 v2 manifest SHA-256 为 `640e3d52a2f7cfc6f991cefe4d111ae18d09ba3260626a2e927988b5cd17a38a`。这些制品继续证明当时的模型、维度、接口、provider、BM25 backend 和无结果读取边界，但旧的五项 Dense 容差与 Sparse exact 重放不再是当前接纳条件；历史 manifest 不覆盖、不重写、不重新签名。

现行在线路由治理固定为 `ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2`：

1. provider-managed Dense 与 Learned Sparse 均不设置数值误差、跨请求 exact 或容差通过线；数值差异只能进入描述性诊断，不能改变接纳结论；
2. 每个获授权的候选快照只调用一次在线 route，先校验 provider/model、输出数量、Dense 维度、Sparse index/value schema、非空、有限值、Chunk/Query ID、目标覆盖和路由失败状态；
3. 结构校验通过后立即固化候选 ID、逐路原始分数/排名、请求/输出摘要、配置指纹与 tie-break，并以 manifest/content root 哈希封存；所有方法共用该快照；
4. 不得因数值差异重跑，不得在多个成功运行中选择分数更稳定、排名更好或更符合预期的一个；transport/API/schema/空向量/NaN/Inf/维度/ID/目标覆盖/manifest 错误仍是硬失败；
5. BM25、指标、bootstrap、文件生成和其他本地确定性计算继续要求精确复现。Gate A 离线运行不得再次调用在线编码服务。

该修订发生在观察 v6-Dev v4/v5 数值差异之后、Gate A 与 Reranker/M1 结果之前。它不改变候选池 estimand、效应阈值、数据分母或 Gate 规则，也不要求重跑已经通过结构与完整性核验的 v5。未来如执行 v3 route preflight，它只作当前模型/schema/结构探针，不生成第二份候选快照，也不提供数值接纳标准。P4-00 仍因双仓非 clean、缺当前版本远端绿色 CI 和正式 `contract-lock.json` 而未完成。

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

唯一内部数据协议为[Internal Stress v13 数据协议](robust-fusion-internal-stress-v6.md)。`scripts/initialize_robust_fusion_internal_v6.py` 已建立本地 gitignored 三分目录、独立 cohort manifest、GateA/Blind 方法访问锁、source/exposure 台账、四张最小摄取模板和全包摘要。协议状态现为 `FORMALLY_ESTABLISHED_DEV_SYNTHETIC_REVIEW_ADJUDICATED_ROUTE_EVIDENCE_VERIFIED`，`gate_eligibility` 仍必须保持 `NOT_ELIGIBLE`；任何 runner 都不得把“目录存在”“Dev 生成成功”“结构提案 30/30”“Dev 人工接纳 28/30”或“Dev 三路证据已核验”解释为“确认性人口已冻结”。

30-family DeepSeek 先导只能写入新的版本化 `runs/robust_fusion/internal_v6_deepseek_pilot_v2/`，不得覆盖 v1 规划包或当前 GateA/Blind 目录。调用只发送生成指令和自包含合成 schema，不上传内部文档、未公开语料或历史逐条数据。每次调用必须先保存提示词 hash，再保存原始响应、响应 hash、模型、时间、重试、token 用量和价格快照；全批次失败不得静默自动重跑。解析器对非法 JSON、缺字段、非原子冲突、证据锚点不逐字、重复 family ID 或来源缺失闭门拒绝。模型输出只能成为待人工复核的提案，不能写入 GateA/Blind 或标为人工真值。

双审主持人入口固定为 `scripts/review_robust_fusion_internal_v6_human.py`。执行顺序只能是 `lock → review → finalize`：`lock` 在解析答案前快照六份 CSV 与冻结输入，`review` 只读取快照并将非逐字但可定位的证据写为警告，`finalize` 保存 A/B 原始值、条款级裁定、family 接纳台账与独立 manifest。当前提交锁 SHA-256 为 `72d8b77ca601c925ff3840afc4812ac1395019d1930548cd98836201adefbb00`，最终 manifest SHA-256 为 `654ff9ff1959aeb18895b8a872c34665c9a262510f13d79146aca6183650b99a`；所有输出仍是 gitignored Dev 制品。

`scripts/materialize_robust_fusion_internal_v6_adjudicated_dev.py` 只读取最终接纳台账，确定性生成 28 条 Query、112 条单段文档、112 条证据标签和 28 条 family assignment。输出固定在 `data/robust_fusion/internal_stress_v6/dev/releases/adjudicated_synthetic_v1/`，release manifest SHA-256 为 `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac`；旧空 manifest 不覆盖，追加 root manifest v9 SHA-256 为 `683e4967097e041a78fd7c5221c462ff4d75243127d8feb761cf7b0d40d7b2ab`。该 release 仅 `annotation_ready=true`，在真实重算 Dense/Learned Sparse/BM25 前仍为 `retrieval_route_evidence_ready=false`。

`scripts/run_robust_fusion_internal_v6_route_evidence.py` 与 `linkrag_eval.robust_fusion.internal_v6_route_evidence` 提供 Dev-only 两阶段入口。`prepare` 只验证固定 release、真实运行配置和 28/112/112/28 闭合关系，并写脱敏计划；`execute` 需要精确确认 token，从第一次远端 collection 探测开始即把计划计为唯一执行尝试，失败写 `FAILED_NO_AUTORETRY`，不自动重试、不删除或覆盖远端状态。输出使用版本化 eval collection、独立 metadata/BM25 SQLite、同一 Dense/Sparse 编码器实例和当前 `candidate_hits/route_hits` 契约，物理分离 `method_view/` 与 `evaluation_view/`。

执行谱系固定为：v1 在零尝试时 `SUPERSEDED_BEFORE_EXECUTION`；v2 plan SHA-256 `4e1e279b12e23436421b4b6166b261451000cd0e86817ada5d77ccd0cea98144` 因缺 SSH 转发在首次 Qdrant probe 超时，0 编码请求且 collection 不存在；v3 plan SHA-256 `14ee97c428b3a0ed460ff29cf2063e0cfd45c6d4969ebdac1d9d44feb5798818` 在健康隧道下因本地 `storage/` 父目录未创建而于 SQLite 打开阶段失败，未发出编码请求且 collection 不存在；v4 plan SHA-256 `98209247819b35304ab26af98befdbff0367fe0046b42f940b8a373132fbabe3` 完成三路物化，但 manifest 纳入运行时 `-wal/-shm`，进程退出后原 content root 不可复算，故原制品不改写、不重签并拒收；修复后另建 v5，plan SHA-256 `a7b159cc7f8f2d694e816b820971a8d3bce85c2f1fe392dde5c4c0003df7c03a`，一次执行完成。

v5 manifest SHA-256 为 `a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d`，content root 为 `1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550`。独立核验确认 28 Query、112 Chunk、3,056 行候选，三路各覆盖 28/28 Query，112/112 已标注候选及 28/28 gold target 入候选并集；metadata SQLite、FTS5 与 Qdrant 112 个点的 Chunk ID 完全一致。方法视图标签泄漏检查通过，Gate A/B 均为 false。跨 v4/v5 候选身份、Top-1、Top-10 和已标注候选排名稳定；在线 Dense 最大绝对分数抖动约 `2.46×10⁻⁴`，所以只声称集合与核心排名可复现，不声称全部浮点逐字节一致。详见[独立核验报告](../reports/internal_v6_dev_route_evidence_v5_verification_2026_08_29.md)。该 runner 仍明确 `formal_p4_02_snapshot=false`。

[C2 三分边界最小补充方案](robust-fusion-c2-boundary-supplement.md)由 `scripts/initialize_robust_fusion_c2_boundary_supplement.py` 初始化为 8 个管理员规划槽和空摄取/标注模板，manifest SHA-256 为 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347`。当前 materialized case/candidate/pair 均为 0、人工未开始、无三路证据；管理员配额与目标类别不得进入后续 A/B 包。

当前实现为 `scripts/run_robust_fusion_internal_v6_deepseek_pilot.py` 与 `linkrag_eval.robust_fusion.internal_v6_pilot`。首批因 DeepSeek V4 默认开启思考模式而有 6 条 `finish_reason=length`；失败批次没有覆盖或整批自动重跑。恢复调用显式发送 `thinking={"type":"disabled"}` 与 `response_format={"type":"json_object"}`，每次只从前一 manifest 的拒绝 ID 生成新版本化目录，并把技术变更、源 manifest、提示词 hash 和校验错误写入审计。五段链最终以 43 次调用得到 30 个结构合格提案；首批结构产率仍固定为 24/30，不能被恢复后的 30/30 覆盖。

P2-01 相似度自动校准入口为 `scripts/run_robust_fusion_similarity_dev_calibration.py`，纯校验与统计位于 `linkrag_eval.robust_fusion.similarity_dev_calibration`。执行器只接受 v5 route manifest/content root 及其绑定的 adjudicated release，路径或 manifest 出现 GateA/Blind 即拒绝；它从 evaluation view 选择 `relevant_gold` 参照成员，从 method view 读取正文，并对禁止字段递归扫描。两个冻结编码器输出 112×768 与 112×512 的 float32 向量，84 个非参照候选按 (S_{qg}(c)) 计算双编码器相似度。正式制品 manifest SHA-256 为 `b44d13f5a5e4f6bea2225ec8c29588db10a37ad1da124eb2d8ff7fb09f08454c`；第二次完整编码对核心文件逐字节重放一致，verifier 复核 24 个受管文件与 112 条向量摘要。A/B 目录各含 24 行 opaque 文本对和空白提交表，不含 evaluation label、模型分数或答案键。提交审阅入口为 `scripts/review_robust_fusion_similarity_human_audit.py`：它验证 A/B 提交锁和仲裁锁、执行机械校验、计算 κ/±1 一致率与仲裁后效度，并封存最终 24 条人评分及 manifest。当前六项人工效度门槛全部 PASS，但共同支持 FAIL，状态为 `REVIEW_COMPLETE_FORMAL_FREEZE_BLOCKED`。

唯一补充周期入口为 `scripts/run_robust_fusion_similarity_support_supplement.py` 与 `linkrag_eval.robust_fusion.similarity_support_supplement`。`prepare` 在任何新分数前锁定 72-family 固定样本量、两侧 100 固定分母、missing-as-miss、v1 全保留、人工双盲和唯一停止规则；lock SHA-256 为 `57179fbf…c6b2b`。`materialize` 生成 72 个确定性 Dev-only 配对微事实与 A/B 各 144 行关系包；`score` 只加载冻结的本地 E5/DistilUSE，生成 216×768/512 向量、144 个候选分数和 A/B 各 48 行相似度包，自动 manifest SHA-256 为 `1c8b0499…327d`。两组向量二次内存重放均 exact。构造角色预览不得代替关系真值。四份提交的后续入口是 `scripts/review_robust_fusion_similarity_support_supplement.py`：真实执行已严格按 `lock-submissions → validate` 完成，提交锁 `7a3ca434…2ae6`；关系 144/144、相似度 48/48 exact 且三类仲裁集合为空。

锁后发现 CLI 缺少零仲裁 finalizer。该缺口以新模块 `linkrag_eval.robust_fusion.similarity_support_finalization` 补齐，性质只是不修改预注册的缺失执行器。真实运行前先执行 `seal-zero-finalizer-implementation`，封存 spec/code manifest `af35908b…499fb`；finalizer 对任一差异、不确定、lock/package/pre-review/ID/行数漂移 fail-closed，不解析 construction-role preview，且只写 append-only `human_review/facilitator/finalization_v1/`。代码封存后 `finalize-zero-adjudication` 单次成功，final manifest `ea40f4f0…f2b35`、receipt `3953e92e…13465`。combined 共同支持 96%/99% PASS；supplement-only/combined E5 overall Spearman 0.1775/0.3968 未达 0.50，二者人工效度均 `INCONCLUSIVE`，联合状态 `P2_TERMINAL_INCONCLUSIVE_GATE_A_UNAUTHORIZED`，不生成正式数值冻结文件。

`scripts/materialize_robust_fusion_internal_v6_human_review.py` 按 generation ID 选择最早结构合格版本，复验五段 manifest、8/8/7/7 配额、跨 family ID/全文唯一性及历史 v5 精确全文 hash，再输出独立 `annotator_a/`、`annotator_b/` 与 `facilitator/`。标注员视图禁止出现 generation/source ID、origin、配额、模型关系标签或构造角色；A/B 各完成 30 条资格、90 条候选、90 条候选对，目录权限 `0700`、文件 `0600`。空白交付 manifest 保持不变，人工答案与最终裁定由主持人目录另行锁定；任何 loader 只能读取最终接纳台账中的 28 个 Dev family，且必须拒绝 GateA/Blind。

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

### 5.4 Internal v6-Dev 三路证据先导的边界

当前 Dev 执行器只验证“冻结 release 能否通过真实三路形成可审计候选证据”，不能替代本章的正式 Candidate Snapshot Generator：

- 输入只允许 release manifest `ad32fbb…` 对应的 28 个已仲裁 synthetic Dev family；
- 候选并集保留逐路 raw score/rank/retrieved flag，方法视图不得出现 source ID、qrel、关系、冲突类型、裁决性、origin、family 或压力链字段；
- 评价视图可以保存人工关系和 family，但不得被方法入口读取；
- runner 拒绝既有输出目录、本地 SQLite 或同名 Qdrant collection，且不提供删除、覆盖或自动重试；
- 单次执行得到的只是 Dev 测量校准制品，固定写 `formal_p4_02_snapshot=false`、`gate_eligibility=NOT_ELIGIBLE`；
- P4-02 仍须等待 clean 双仓、绿色 CI、`contract-lock.json`、正式压力链 schema 与全部冻结数据人口。

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

### 9.1 人工作业浅入口

版本化 `runs/` 路径是机器证据位置，不是人工操作界面。所有需要研究员、仲裁员、curator、研究负责人或独立审稿人直接读写文件的任务，必须额外建立项目根目录相对的 `human_tasks/<task-id>/` 浅入口，并遵守[人工作业浅入口规范](robust-fusion-human-task-entrypoints.md)。

工程硬约束如下：

- 人工指南与聊天交接只使用 `human_tasks/<task-id>/...`，不得要求参与者识别 canonical run ID 或日期目录；
- 浅入口以相对符号链接指向唯一 canonical 包，不复制可编辑任务；
- 不同评审角色使用不同 task ID，入口不能暴露其他评审者答案、facilitator key、模型分数或 Gate 结果；
- canonical 包存在但浅入口未建立或未校验时，只能记录为“机器包完成”，不能记录为“可交付”；
- 提交仍写入 canonical 包并按原始字节先锁后读；浅入口不改变固定分母、manifest 或 finalizer；
- Blind 人工入口只能建立在独立 curator 工作区，主方法工作区只接收 opaque ID/hash 与资格状态，不能出现指向 Blind 正文的链接；
- 项目外传递使用独立导出/回收包，不直接压缩包含符号链接的项目内入口。

机器注册表为 `docs/plans/robust-fusion-human-task-registry.json`；交付前执行：

```bash
PYTHONPATH=src .venv/bin/python scripts/check_robust_fusion_human_task_entrypoints.py --before-handoff
```

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
- 本地确定性计算必须逐位一致；provider-managed Dense/Sparse 只执行结构合法性与单次快照哈希封存，不设数值误差或跨请求 exact 门槛，也不得因数值差异重跑或择优。
- 任何人工包必须先通过浅入口路径深度、链接目标、角色隔离、允许文件、行数、指南泄漏和预交付输出不存在性校验，才能标记为可交付。

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
| 把 Internal v6 空骨架或 Dev 合成先导当作已封存 cohort | Gate A/B 运行在无独立自然来源/人工真值或事后填充数据上 | root manifest 明示 `NOT_ELIGIBLE`；Dev 输出物理隔离且 runner 拒绝读取；只有非空、自然配额、双审、family 零交集、功效分母与 seal 全部通过才解锁 |
| cMedQA2 全文误入版本库或公开复现包 | 违反已确认的非商业本地使用治理并扩大数据暴露 | 原始 zip/正文只留在 gitignored 数据目录；版本化产物仅存 commit、ID、hash、派生标签、排除表和 loader；CI 检查禁止正文文件进入 seal |
| 历史 collection 更“完整” | 容易误拼不同模型和版本 | 单快照只绑定一个冻结 collection/backend |
| 历史 BGE-M3/Alt Embedding 被误接回正式研究 | route 口径错误，相似度不可复算 | Gate A preflight 对 BGE provider/model 直接拒绝；历史 sidecar 只读追溯，不复用、不重算 |
| Reranker API 或模型漂移 | 结果不可重复 | 冻结模型 ID/revision/参数并缓存原始分数 |
| LinkRag 当前 HEAD 与 Eval 旧 CI pin 漂移 | 现有 `BucketRouter` 适配无法代表当前生产候选契约 | 按第 3.4 节修 Eval 薄适配、更新精确 CI pin，并以 clean `contract-lock.json` 和绿色 run/report 验收 |
| 双仓 SHA 对应 dirty 工作区 | 相同 SHA 可能运行不同的未提交内容 | 预检记录 diff/untracked hash；正式快照只接受 `dirty=false` 的 commit/tag |
| Seal、root hash 与时间戳互相引用 | 产物无法形成唯一无环指纹 | 先冻结 root manifest，再时间戳 root hash；receipt 只作不进入 root hash 的追加 sidecar |
| evaluator 字段泄漏 | 方法结果虚高 | 物理视图隔离和置换不变性测试 |
| 在线服务波动 | 部分 Query 缺路、超时或数值变化 | route preflight 只检验模型/schema/结构；正式快照单次生成后哈希固化。transport/API/schema/空向量/NaN/Inf/维度/ID/目标覆盖错误显式失败；数值差异不触发重跑或择优，离线阶段不调用在线服务 |
| 计算预算超限 | 无法完成全矩阵 | 按科研协议的缩减顺序执行，不降低核心证据标准 |

## 13. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-08-30 | v23 | 将人工作业界面与机器证据目录正式分层：所有后续标注、双审、仲裁、签署和独立评审在交付前必须建立 `human_tasks/<task-id>/` 浅入口并通过机器校验；当前 R2 仲裁已落地。Blind 继续物理隔离，只能在 curator 独立工作区使用同样的浅入口，不向方法开发工作区暴露正文或链接 |
| 2026-08-29 | v22 | 四份补充提交先锁后验且零仲裁；补齐已冻结 protocol 的零仲裁 finalizer，合成测试后先封存 post-lock spec/code、再单次真实执行。combined 共同支持 96%/99% PASS，但 supplement-only/combined 人工效度均 `INCONCLUSIVE`；terminal `INCONCLUSIVE`，无正式数值冻结、无第三轮，不授权或运行 readiness/Gate A/B |
| 2026-08-29 | v21 | 永久保留 v1 `INCONCLUSIVE`；新增唯一一次 72-family Dev 共同支持补充执行器。预注册/样本量/分母/缺失/合并/停止规则先锁后算，本地双编码器 216 条向量 exact 重放，生成 144 分数、A/B 各 144 行关系包和各 48 行相似度包；状态 `AWAITING_HUMAN_SUBMISSIONS`，不授权 Gate A/B |
| 2026-08-29 | v20 | 相似度仲裁提交按先锁后读完成 9/9 行机械核验；finalizer 形成 24 条唯一最终人评分，E5 overall/short/long、DistilUSE overall 与最高主分带两项人工指标全部 PASS。新增仲裁锁漂移拒绝、最终 manifest 和 11/11 谬误扫描；共同支持仍 FAIL，联合冻结 `INCONCLUSIVE`，不完成 P2-01/P2-04 或 Gate A/B |
| 2026-08-29 | v19 | 新增 P2-01 人工提交审阅器；A/B 两份真实提交先锁后比，24/24 行机械校验通过，κ=0.9484、±1=100%。生成 9 行无模型分数/关系标签的最小真实人工仲裁包；状态为 `AWAITING_HUMAN_ADJUDICATION`，不执行人工代填、正式分带或 Gate A/B |
| 2026-08-29 | v18 | 新增 P2-01 Dev-only 相似度执行器、参照集合/向量/分数封存、长短与关系分层、共同支持/分带 provisional 规则、双次确定性重放及 A/B 无答案键正式包。当前共同支持覆盖未过 60% 门禁且人工未提交，状态保持 `AWAITING_HUMAN_SUBMISSIONS`；不完成 P2-01/P2-04/P4-02，不授权或运行 Gate A/B |
| 2026-08-29 | v17 | 以 `ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2` 取代现行 Dense 五项容差/Sparse exact 重放 Gate：在线 Dense/Sparse 单次生成、结构校验、哈希封存，数值差异只作描述且禁止据此重跑或择优；本地确定性计算仍须 exact。旧 v1/v2/诊断制品保持不可变历史证据，v5 无需重跑；未改变科学 estimand、阈值或人口 |
| 2026-08-29 | v16 | 保留 v2/v3 失败与 v4 manifest 完整性拒收，修复 storage 预建、SQLite checkpoint/瞬态 sidecar 排除及 completed state content-root 记录；独立 v5 一次执行并通过 plan/manifest/root、双视图、SQLite/FTS5、Qdrant 112 点和三路覆盖核验。Dev-only、`NOT_ELIGIBLE` 与 `formal_p4_02_snapshot=false` 边界不变 |
| 2026-08-29 | v15 | 记录获确认的 v2 唯一执行在首次 Qdrant existence probe 因直连 `ReadTimeout` 失败并封存：0 Dense/Sparse 请求、0 collection、无重试。只读诊断确认 Qdrant 仅在 `linkcv` 本机监听；恢复本地 36333 SSH 隧道并通过 healthz，另备 v3 `PREPARED` 计划等待新确认，不复用 v2 |
| 2026-08-29 | v14 | 新增 Internal v6-Dev 两阶段三路证据执行器：固定 release、隔离 eval collection/SQLite、同编码器写读、当前候选契约、双视图泄漏门禁、从首次远端探测计入唯一尝试及失败不重试；冻结唯一 `PREPARED` v2 计划但尚未执行。另初始化 8 槽 C2 Dev-only 空白补充包；两者均不完成正式 P4-02 或解锁 Gate |
| 2026-08-29 | v13 | 新增 Internal v6 双审主持人锁定/比较/最终化入口；六份提交先锁后比，机械错误 0，候选级标签全一致、候选对 89/90 一致。保存唯一分歧裁定、模型构造角色偏差和 28/30 人工接纳台账；GateA/Blind 仍 `NOT_ELIGIBLE` |
| 2026-08-29 | v12 | 执行 v11 冻结的 30-family Dev 先导：加入逐调用重试计数、显式非思考 JSON 模式、只补拒绝 ID 的不可覆盖恢复链、逐字锚点/原子替换闭门校验、历史精确全文重合审计和 A/B 隔离盲审包。固定首批结构产率 24/30、全链 43 次调用与恢复后 30 个待审提案；不写 GateA/Blind，不产生人工真值 |
| 2026-08-29 | v11 | 同步科研协议 v20 与 Internal 协议 v7：P2-05 通过后允许新的 v2 运行目录执行 30-family DeepSeek 受控合成 Dev 先导；冻结“不上传私有语料、逐调用审计、闭门 schema/原子性校验、模型不是真值、Dev 与 GateA/Blind 物理隔离”工程契约，Gate 资格继续为 `NOT_ELIGIBLE` |
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
