# 研究重构盘点与删除候选清单

> 日期：2026-09-06。性质：供负责人审阅的盘点，不是删除授权、算法冻结或实验执行协议。
> 本轮只新增本清单、文件台账，并在 CURRENT_STATUS 添加盘点入口；不删除、移动、重命名既有资产，不修改实现，不训练、不运行旧研究流程。

## 1. 本次采用的边界

负责人最新要求是：研究方法保持暂定，不强行构建具体方法；考虑分支混合了大量内容，后续调整必须覆盖文档、代码、测试、配置和数据引用；本轮先列删除清单，绝不真正删除。

当前保留三路召回之后、固定候选、仅使用排序已有输入的研究边界。研究仍关注查询相关的局部区别如何被排序表示保留和利用。**“候选差异帮助选择检查位置”只是候选问题与机制，不是已经选定的唯一主线或正式算法。** 不冻结差异窗口公式、四版本数量、窗口 8、编辑距离 0.2、某种切分器或聚合方式，也不预先创建替代实现。

旧文本比较器、专门三路门控、局部交换、R1/R2 相似度测量和 Gate 流程不再自动成为新研究的必经步骤。保留历史状态与封存边界，不将“退出新研究主线”写成“旧流程已经完成、实验结论被推翻或数据可以删除”。

本次清单中的分类：

| 分类 | 后续含义 | 本轮动作 |
| --- | --- | --- |
| 低风险删除候选 | 文件夹元数据或已核对的字节重复副本 | 仅列名，未删除 |
| 条件性退役／删除候选 | 旧流程专用实现、脚本及测试；先保全、拆分复用内容和解除依赖 | 仅列名，未删除 |
| 改写 | 活动入口、过时主张或通用代码中的旧研究措辞 | 列出需改写位置，不全面改写 |
| 历史保留／归档身份 | 撤销“当前实施要求”身份，保留原文和原证据 | 不移动、不改冻结正文 |
| 保留／待核查 | 活动能力、原始数据、人工提交、锁、共享缓存和未跟踪成果 | 不清理 |

**“归档”首先指阅读与执行身份变化，不等于迁移物理路径。** 有些旧协议、代码和测试参与哈希封存，增加页头或移动路径也可能破坏历史核验。

## 2. 盘点范围与核对基点

- 分支：`robust-fusion-research`。
- HEAD：`1d28732a706e1517229eba9df509363af64f3a77`；本地比远端跟踪分支领先 2 个提交，本轮未 fetch、commit 或 push。
- 本地 master／共同基点：`c275ca01bdf49ee8b4d2ce4dd7fbe1ceb4652286`。
- 共同基点至 HEAD：151 个文件变化，45,635 行新增、1,025 行删除。这是历史分支差异，不是本轮修改量。
- 开始时 Git 跟踪 496 个路径、另有 11 个未跟踪路径，共 507 个路径；未跟踪路径包括目录符号链接，不能全部按普通文件计数。
- 深入静态审查：24 个 `robust_fusion` 源码文件、47 个相关脚本、25 个相关测试，另核对共享召回／存储适配、CLI、配置、CI、依赖与文档入口。
- 对上述源码树做静态 import 检查，收集 227 条研究／脚本导入记录；未发现研究目录之外的核心 `src` 文件静态导入 `linkrag_eval.robust_fusion`。脚本另有裸模块导入、路径常量和哈希清单，不能只依赖这个结果删除。
- ignored 数据只检查名称、目录元数据、Git 忽略状态和符号链接；不读记录、不查数据库、不连接远端、不读取封存 Blind 或撤回结果。PDF 去重只做文件哈希核对。

逐路径台账见 [JSON 清单](research-restructure-inventory-2026-09-06.json)。其中记录 Git 状态、分支变化、建议分类、理由与必要的依赖提示。未变化的既有通用文件保守归入保留，不代表已逐行重审全仓业务逻辑。

### 未提交资产必须单独保全

开始时 6 个 tracked 文件有修改：

- `docs/CURRENT_STATUS.md`
- `docs/plans/robust-fusion-engineering.md`
- `docs/plans/robust-fusion-r2-adjudicator-beginner-guide.html`
- `docs/plans/robust-fusion-r2-gate-a-delta-checklist.md`
- `docs/plans/robust-fusion-todo.md`
- `scripts/audit_robust_fusion_gate_a_readiness.py`

另有研究讨论原稿、人工作业 registry／入口／模块／测试等 11 个未跟踪路径，全部在 JSON 中按开始时状态列出。**HEAD 不是这些修改和 ignored 原始产物的备份。** 不以恢复 master、批量 checkout 或清空未跟踪文件实现重构。

## 3. 真正的低风险删除候选：2 项

| ID | 精确路径 | 依据与未来条件 |
| --- | --- | --- |
| D01 | `docs/.DS_Store` | macOS 文件夹显示元数据，不承担科研含义。本轮仍保留。 |
| D02 | `docs/papers/Language Model Re-rankers are Fooled by Lexical Similarities〔重复副本〕.pdf` | 与同目录无“〔重复副本〕”后缀的主 PDF 字节相同；未来仅可去掉副本，主文件保留。先处理文献地图中的副本引用与历史盘点说明。 |

两个 PDF 均为 604,585 字节，SHA-256 均为 `1e80e5bfc6352d932f7ccbd72e9b9ac13bfedda501bf0a52256c5c745cbe95d6`。`robust-fusion-literature.md` 约第 216、445 行仍提到副本；不能删完留下失效引用。Markdown 与 HTML 配套报告不按字节重复垃圾处理。

## 4. 旧流程的条件性退役清单

这些项目列入“未来可从活动源码树移除”的候选，不表示已经可以整文件删除。只有旧流程退出活动执行、历史源码和未提交修改可追溯、保留能力完成拆分、引用与测试同步处理后，才考虑移除对应文件。精确文件逐项列于文末和 JSON；不提供删除脚本或通配符执行命令。

| 分组 | 候选内容 | 删除前必须处理 |
| --- | --- | --- |
| D10 模型资格包装 | 固定 Qwen／Jina reranker、E5／DistilUSE 资格验证脚本 | 保留模型身份、资格记录和历史结果；新方法未确定，不把旧模型资格变成新前置任务。共享运行环境不随脚本删除。 |
| D11 Gate 包装 | Gate A 数据资格准备、readiness 审计及专用测试 | 资格／曝光数据仍保留；剥离可用校验原则；不运行 readiness 验证“是否可以删除”。 |
| D12 Internal v6／C2 | 受控生成、双审、仲裁物化、Dev 路由证据及专用测试 | 人工提交、release、候选证据完整保留；先评估候选序列化和输入隔离校验是否需要抽离。 |
| D13 P2／相似度校准 | 桌面校准、补包、相似度编码、共同支持、人工审阅／finalizer | 旧失败证据不删；共享 JSON／hash helper 先拆分或随整条消费者链一起退役。 |
| D14 R2 | 来源生成／恢复／锁定、自动测量、功效、诊断、人工终审及测试 | 以完整依赖组审查。旧 DeepSeek source v1–v6 的计划与运行制品已按历史指令删除，不意味着同名代码没有被 v7 调用；v7 来源仍保留。 |

### 不能按版本号删除的实际依赖

- `r2_source_authorship_v7.py` 仍引用 `r2_source_generation.py`、`r2_source_execution_v2.py`、`r2_source_recovery_v5.py`、`r2_measurement.py` 和 `similarity_dev_calibration.py`。
- v5 又借用 v4、execution v2、generation 等模块；measurement／power／diagnostic 之间仍有导入。保留 v7 时不能先删旧版本基础模块。
- `scripts/run_robust_fusion_r2_measurement.py` 的 `CODE_FILES` 明确写入源码、脚本、测试的路径并参与哈希。代码迁移后不能继续声称新文件就是当时封存的原文件。
- 部分审阅脚本互相导入，不只是 CLI 包装。未来应按源码、脚本、测试、文档、manifest 引用一组核对。

### 有复用价值，暂不列入整文件删除的内容

| 文件／接口 | 建议 |
| --- | --- |
| `src/linkrag_eval/robust_fusion/similarity.py` | 文本规范化、float32 指纹、float64 余弦是可复用资产；不是新研究必须使用相似度编码器的理由。 |
| `src/linkrag_eval/robust_fusion/replay_contract.py` | 向量结构检查／指纹／诊断可保留；旧 provider 协议 ID 与准入结论应与通用能力分开。 |
| `src/linkrag_eval/robust_fusion/__init__.py` | 随最终保留模块调整导出，当前不直接删包。 |
| `scripts/probe_robust_fusion_route_contract.py`、`scripts/diagnose_robust_fusion_dense_replay.py` | 诊断脚本直接导入 probe；可拆分通用路由契约检查，旧研究 profile 和“重放 Gate”包装另行退役。 |
| `src/linkrag_eval/robust_fusion/human_task_entrypoints.py`、checker、对应测试 | 注册表驱动的浅入口校验有通用价值；若后续迁移，同时更新 import、默认 registry 路径、HTML 和 symlink 映射。 |

上表多数函数目前没有非研究核心源码消费者，保留的是可复用设计资产，不能据此声称整个旧包都是运行主链硬依赖。

另有两个**混合模块**位于条件性清单中，必须先检查拆分：

- `internal_v6_route_evidence.py` 的 `ensure_method_view_safe`、`serialize_candidate_response` 提供评价字段隔离、分路分数／排名／并集检查；`build_identity_maps`、`build_views` 则绑定旧 Dev release 和人工标签，不能整段改名充当新通用快照。
- `similarity_dev_calibration.py` 的 JSON／hash helper 被其他旧模块借用；读取冻结 Dev、旧授权载入和正式分带计算属于旧流程。

## 5. 文档需要全面调整，但大多应保留

### 后续优先改写的入口

| 路径 | 当前问题 | 后续建议 |
| --- | --- | --- |
| `README.md` | 把旧 HANDOFF 作为当前交接，部分工程进度仍是早期描述 | 保留项目入口，指向唯一当前状态，分开工程状态和研究暂定范围。 |
| `docs/CURRENT_STATUS.md` | 顶部说方法未定，后文仍将 R2／Gate 当主阻塞 | 后续整理为当前研究、现有工程、历史流程三层；R1/R2 的事实与封存约束不改。本轮仅追加盘点入口。 |
| `docs/HANDOFF.md` | 仍标 2026-07-28、旧分支、CI 未跟踪与旧 pin | 保存旧交接身份后重写导航，不把旧命令当本轮待办。 |
| `docs/README.md` | “当前专题”仍直达旧冻结协议 | 显示方法暂定入口；旧流程移入历史导航，不删除正文。 |
| `docs/DOCUMENT_CATALOG.md` | 旧科研 v26／工程 v17 被列为当前；新讨论稿与部分 R2 专项未收录 | 更新文档身份和替代关系；避免重复维护项目进度。 |
| `docs/reports/REPORT_INDEX.md`、`scripts/build_report_index.py` | 历史用途与当前流程边界需清楚 | 保留索引与工具；后续按保留资产更新描述，不借重建索引触碰封存结果。R2 命名的 failure diagnostic 实际诊断 R1，应注明。 |
| `docs/plans/research-direction-review-2026-09-06.md` | 记录截至独立审查与静态核对的讨论 | 保留所有问答原文和证据，后续追加讨论状态；不把附件建议写成算法批准。 |

### 退出活动执行身份、保留原文的协议

`robust-fusion-research.md`、`robust-fusion-engineering.md`、`robust-fusion-todo.md`、`robust-fusion-publication.md`，以及 R1/R2、Internal v6、C2、相似度 manifest、标注手册、旧审稿答复与中文选题文档，均建议归入历史协议身份。逐路径分类见文末与 JSON。

其中 `robust-fusion-human-task-registry.json` 与 `robust-fusion-r2-adjudicator-beginner-guide.html` 还连接真实人工作业入口，暂列“保留映射、待同步处理”，不视为重复副本。

旧科研、工程、todo、发表文档在 docs 中分别有 27、14、9、10 处引用位置。后续不能只移动几个主文件而不处理导航、代码常量、manifest 和浅入口。对参与封存的原文，优先在外部索引说明历史身份。

### 明确保留的研究证据

- `docs/experiments/ltr-fusion-v1.md`，尤其直接 Qwen 重排与旧 LambdaMART 附加 Qwen 分数的负结果；历史条件、版本、原始记录缺口照实保留。
- `docs/reports/` 下全部实证、审计、人工核验、配套 JSON／SHA／HTML；不能将 R1 `INCONCLUSIVE` 改为成功，也不能把 R2 待仲裁改成终审完成。
- `docs/plans/robust-fusion-literature.md`、`robust-fusion-evidence.md`、`docs/papers/README.md` 与论文主文件；旧“已冻结空缺”等措辞只作为历史身份解读。
- `docs/plans/post-recall-relational-fusion-concept-2026-09-05.md` 与独立审查记录：保留研究演进和手工表示检查，不因此继续实施旧结构。
- 已有 `docs/archive/design-v1/` 15 份设计与归档说明、架构、Golden 计划、Query 重写／软分流历史实验。

## 6. 必须保留的共享工程能力

**不得整体回退到 master。** 本分支同时包含适配当前生产依赖的工程修复：

| 路径／组件 | 保留原因与仅需审查的局部内容 |
| --- | --- |
| `src/linkrag_eval/retrieval/learning_to_rank/` 与 `models/candidate-difference-v3-20260728-final33/` | 现有 38 维基线、在线契约、模型包、回退与测试向量；原始 baseline 保留，新方法不得直接覆盖冻结包。 |
| `src/linkrag_eval/retrieval/recall_adapter.py` | `execute_candidate_contract_once` 保留未截断候选和分路信息，并将生产类型约束在白名单 adapter；名称含研究不等于功能过时。 |
| `src/linkrag_eval/retrieval/recall_factory.py`、`src/linkrag_eval/store/vector_store.py` | 当前 Qdrant 显式 collection、named dense、SQLite FTS5 和前缀隔离适配；不可回退到已删除的生产 BucketRouter／qdrant_bm25 接口。仅旧 Gate A 提示语需后续改写。 |
| `.github/workflows/ci.yml`、`pyproject.toml`、`uv.lock` | 精确 LinkRag pin 与依赖安装可复现性；没有独立 robust-fusion 依赖组，不能连带删除 numpy、httpx 等共享依赖。 |
| `tests/contract/test_ltr_v3_contract.py`、`tests/contract/test_recall_factory.py` | LTR 固定向量、生产契约、完整候选并集与适配测试有独立价值；研究 profile 字符串与注释可以后续整理。 |
| `src/linkrag_eval/judge/eval_llm.py`、对应测试 | retry 记录、thinking／JSON 参数为共享客户端扩展，不能因最初服务旧研究就回退。 |
| `src/linkrag_eval/llm/dense_client.py`、`sparse_client.py`、`.env.eval.example` | 保留现有和历史兼容能力；仅旧研究口径描述另审。真实 `.env.eval` 不读取、不清理。 |
| CLI、config、compute、store、metrics、reporters、runners、golden、query_rewrite、alembic、import 边界 | 独立评测项目能力；没有因研究方向变化而整块删除的依据。历史工具不等于新实验授权。 |

`AGENTS.md` 与架构中关于 BucketRouter、named vector 的历史表述还需对照现有适配补齐说明，但只能同步实际实现，不能借研究重构放松 eval 前缀、SQLite 自持和 import 白名单。

## 7. 本地数据、人工提交和缓存：保护／待核查

以下为普通文件数和逻辑字节总和，不跟随符号链接，也不代表实际磁盘占用；父子目录不能相加重复计数。

| 路径 | 普通文件数 | 字节 | 建议 |
| --- | ---: | ---: | --- |
| `runs/` | 833 | 345,847,662 | ignored，全部先保护 |
| `runs/robust_fusion/`（上项子集） | 826 | 24,512,366 | 原始研究证据，保护 |
| `runs/` 根层数据库及 sidecar（上项子集） | 7 | 321,335,296 | 不按文件大小或 sidecar 后缀判断冗余 |
| `data/robust_fusion/public/` | 36 | 4,454,569,389 | 未来核查下载来源与可恢复性，当前保留 |
| `data/robust_fusion/models/` | 101 | 3,460,032,333 | 未来核查模型消费者与缓存引用，当前保留 |
| `data/robust_fusion/derived/` | 51 | 86,003,536 | 含曝光排除、来源映射、资格与人工材料，保护 |
| `data/robust_fusion/internal_stress_v6/` | 38 | 226,853 | Dev、控制记录和访问锁，保护 |
| `models/` | 7 | 72,351 | 全部 tracked，活动 LTR 制品与说明，保护 |
| `human_tasks/` | 1 | 714 | 另有 3 个 symlink，未跟踪，保护 |
| `linkrag-eval-sqlite-share-20260827/` | 5 | 321,270,817 | 不能未经核对视为数据库冗余副本 |

保护重点包括 `runs/robust_fusion/` 下的 `r2_measurement_v1/`、v7 来源／准备、v7.1 锁准备、P2 人工校准、相似度 v1 与唯一补充、Internal Dev 证据、`recovery/`、`contracts/`、`gate_a/`。这些名称不构成可删除依据。具体元数据子目录见 JSON。

- `human_tasks/r2-adjudication/START_HERE.html` 链接到 tracked 指南；`relation/`、`similarity/` 链接到 R2 `human_review/adjudication_v1/` 的真实目录。删除浅入口不能递归到 canonical 数据。
- 本地模型缓存有 48 个 snapshot symlink，目标在同一缓存树的 blobs；另有 48 个零字节 lock，不能据此认定锁失效。
- `/Users/kawauso/.cache/huggingface` 是仓库外共享边界，仅确认目录存在；没有核查使用者，不纳入删除范围。`.agents/`、`.ai/`、虚拟环境与其他项目也不因本次研究重构清理。
- `golden/`、`runs/golden_v2/` 本地不存在，只记录缺失；不重建、不从废纸篓恢复、不重新下载以凑齐目录。历史报告所引用的旧原始记录不因此被认为已备份。
- 已按负责人早前要求移除的旧 source 制品和撤回的 decision/readiness 输出，不恢复取证。

**当前没有任何 ignored 原始研究数据、人工材料或运行证据被认定为可直接删除。** 公共下载、模型缓存、数据库分享副本和派生版本只是未来待核查对象，不是本轮删除候选。

## 8. 未来实施顺序与停止点（仅计划）

1. 先审阅本清单。研究方法继续暂定；明确某文件是“退出当前执行”还是“物理移除”。
2. 在任何移除前保全当前 dirty／untracked 文件，以及 Git 未覆盖的原始证据；验证备份／映射确实可恢复。当前 HEAD 只能覆盖已提交源码。
3. 先整理活动导航与旧协议的历史身份；涉及哈希封存的正文不直接加页头。人工作业入口保留历史映射，避免仍把旧任务展示成新研究前置。
4. 逐组处理旧研究代码；只抽离已经识别的通用能力，不为尚未确定的方法预建新框架。依赖未解除、外部使用不明或备份不完整时，该组不删。
5. 实现真正发生变化后，再运行适当单测、导入边界、保留的 LTR／召回契约及文档链接检查。旧 finalizer、readiness、Gate、Blind、编码 API 不属于清理验收命令。
6. 重建报告索引前先核对工具扫描范围和保留路径，不用索引生成器读取封存原始结果或覆盖历史报告。

不把“新方法尚未实现”当作清理失败，也不把“旧原型无效”扩写成所有候选比较方法均无效。本次没有恢复、重跑或重新标注任何历史实验。

## 9. 静态审查限度与本轮核验

- 静态引用可发现本仓库直接消费者，不能证明没有外部调用、动态路径或进程正在使用本地缓存；这些保留在未来核查条件中。
- ignored 资产是元数据盘点，不宣称已核验其内容完整性、标签填写状态或备份一致性。
- 本轮检查通过：JSON 可解析、分类数量一致、509 个台账路径仍存在、符号链接目标未变；除已声明的 CURRENT_STATUS 追加内容外，台账中可比对的 157 个既有文件 SHA-256 均未变。tracked 修改路径仍为开始时的 6 项，新增文件仅本次两份清单。ignored 数据没有内容级核验；不运行代码测试，因为实现没有修改。

<!-- GENERATED-INVENTORY-START -->

## 10. 精确逐文件列表

以下按类别列出待审路径；仅 D10–D14 的 86 项属于条件性退役候选，其余分别为历史保留、复用审查、映射保护和后续改写。所有条目均为 `executable_now=false`；低风险两项见第 3 节。通用资产和全仓其余文件逐项见 JSON。

| 分类 | 路径数量 |
| --- | ---: |
| A01 · historical_identity_preserve_bytes | 21 |
| D01 · low_risk_delete_candidate | 1 |
| D02 · deduplicate_after_reference_review | 1 |
| D10 · conditional_retirement_candidate | 2 |
| D11 · conditional_retirement_candidate | 3 |
| D12 · conditional_retirement_candidate | 13 |
| D13 · conditional_retirement_candidate | 17 |
| D14 · conditional_retirement_candidate | 51 |
| H01 · hold_reusable_review | 7 |
| H02 · hold_human_mapping | 9 |
| K01 · preserve_evidence | 55 |
| K02 · preserve_active_baseline | 16 |
| K03 · preserve_existing_scope | 289 |
| R01 · rewrite_navigation | 6 |
| R02 · preserve_shared_review_wording | 18 |

### D10 · 旧固定模型资格包装；保留资格结果/模型身份/环境，未来整组退役前保全源码。

- `scripts/qualify_robust_fusion_rerankers.py`
- `scripts/qualify_robust_fusion_similarity_encoders.py`

### D11 · 旧Gate资格/readiness流程；数据和曝光排除保留，不以运行Gate验收清理。

- `scripts/audit_robust_fusion_gate_a_readiness.py`（开始时有未提交修改）
- `scripts/prepare_robust_fusion_gate_a_eligibility.py`
- `tests/unit/test_robust_fusion_gate_a_readiness.py`

### D12 · 旧Internal/C2流程；先保全人工/候选证据，并审查序列化与输入隔离能力的抽离。

- `scripts/initialize_robust_fusion_c2_boundary_supplement.py`
- `scripts/initialize_robust_fusion_internal_v6.py`
- `scripts/materialize_robust_fusion_internal_v6_adjudicated_dev.py`
- `scripts/materialize_robust_fusion_internal_v6_human_review.py`
- `scripts/review_robust_fusion_internal_v6_human.py`
- `scripts/run_robust_fusion_internal_v6_deepseek_pilot.py`
- `scripts/run_robust_fusion_internal_v6_route_evidence.py`
- `src/linkrag_eval/robust_fusion/internal_v6_pilot.py`
- `src/linkrag_eval/robust_fusion/internal_v6_review.py`
- `src/linkrag_eval/robust_fusion/internal_v6_route_evidence.py`
- `tests/unit/test_robust_fusion_c2_boundary_supplement.py`
- `tests/unit/test_robust_fusion_internal_v6_pilot.py`
- `tests/unit/test_robust_fusion_internal_v6_route_evidence.py`

### D13 · 旧P2/相似度校准与补充；先处理共享JSON/hash函数、交叉导入、历史失败证据。

- `scripts/materialize_robust_fusion_p2_human_delivery.py`
- `scripts/prepare_robust_fusion_p2_calibration.py`
- `scripts/prepare_robust_fusion_p2_calibration_patch.py`
- `scripts/prepare_robust_fusion_p2_calibration_replay.py`
- `scripts/review_robust_fusion_p2_calibration_patch.py`
- `scripts/review_robust_fusion_p2_calibration_replay.py`
- `scripts/review_robust_fusion_similarity_human_audit.py`
- `scripts/review_robust_fusion_similarity_support_supplement.py`
- `scripts/run_robust_fusion_similarity_dev_calibration.py`
- `scripts/run_robust_fusion_similarity_support_supplement.py`
- `src/linkrag_eval/robust_fusion/similarity_dev_calibration.py`
- `src/linkrag_eval/robust_fusion/similarity_support_finalization.py`
- `src/linkrag_eval/robust_fusion/similarity_support_supplement.py`
- `tests/unit/test_robust_fusion_similarity_dev_calibration.py`
- `tests/unit/test_robust_fusion_similarity_human_review.py`
- `tests/unit/test_robust_fusion_similarity_support_human_review.py`
- `tests/unit/test_robust_fusion_similarity_support_supplement.py`

### D14 · 旧R2完整依赖组；v7仍依赖早期模块，保全路径/哈希清单，不能按版本删除。

- `scripts/prepare_robust_fusion_r2_automatic_execution.py`
- `scripts/prepare_robust_fusion_r2_source_authorship_v7.py`
- `scripts/prepare_robust_fusion_r2_source_execution_v2.py`
- `scripts/prepare_robust_fusion_r2_source_generation.py`
- `scripts/prepare_robust_fusion_r2_source_lock_v7_1.py`
- `scripts/prepare_robust_fusion_r2_source_recovery_v3.py`
- `scripts/prepare_robust_fusion_r2_source_recovery_v4.py`
- `scripts/prepare_robust_fusion_r2_source_recovery_v5.py`
- `scripts/prepare_robust_fusion_r2_source_recovery_v6.py`
- `scripts/review_robust_fusion_r2_human.py`
- `scripts/run_robust_fusion_r2_automatic_execution.py`
- `scripts/run_robust_fusion_r2_measurement.py`
- `scripts/run_robust_fusion_r2_measurement_power.py`
- `scripts/run_robust_fusion_r2_measurement_power_v2.py`
- `scripts/run_robust_fusion_r2_similarity_diagnostic.py`
- `scripts/run_robust_fusion_r2_source_authorship_v7.py`
- `scripts/run_robust_fusion_r2_source_execution_v2.py`
- `scripts/run_robust_fusion_r2_source_generation.py`
- `scripts/run_robust_fusion_r2_source_lock_v7_1.py`
- `scripts/run_robust_fusion_r2_source_recovery_v3.py`
- `scripts/run_robust_fusion_r2_source_recovery_v4.py`
- `scripts/run_robust_fusion_r2_source_recovery_v5.py`
- `scripts/run_robust_fusion_r2_source_recovery_v6.py`
- `src/linkrag_eval/robust_fusion/r2_automatic_execution.py`
- `src/linkrag_eval/robust_fusion/r2_human_review.py`
- `src/linkrag_eval/robust_fusion/r2_measurement.py`
- `src/linkrag_eval/robust_fusion/r2_measurement_power.py`
- `src/linkrag_eval/robust_fusion/r2_measurement_power_v2.py`
- `src/linkrag_eval/robust_fusion/r2_similarity_diagnostic.py`
- `src/linkrag_eval/robust_fusion/r2_source_authorship_v7.py`
- `src/linkrag_eval/robust_fusion/r2_source_execution_v2.py`
- `src/linkrag_eval/robust_fusion/r2_source_generation.py`
- `src/linkrag_eval/robust_fusion/r2_source_lock_v7_1.py`
- `src/linkrag_eval/robust_fusion/r2_source_recovery_v3.py`
- `src/linkrag_eval/robust_fusion/r2_source_recovery_v4.py`
- `src/linkrag_eval/robust_fusion/r2_source_recovery_v5.py`
- `src/linkrag_eval/robust_fusion/r2_source_recovery_v6.py`
- `tests/unit/test_robust_fusion_r2_automatic_execution.py`
- `tests/unit/test_robust_fusion_r2_human_review.py`
- `tests/unit/test_robust_fusion_r2_measurement.py`
- `tests/unit/test_robust_fusion_r2_measurement_power.py`
- `tests/unit/test_robust_fusion_r2_measurement_power_v2.py`
- `tests/unit/test_robust_fusion_r2_similarity_diagnostic.py`
- `tests/unit/test_robust_fusion_r2_source_authorship_v7.py`
- `tests/unit/test_robust_fusion_r2_source_execution_v2.py`
- `tests/unit/test_robust_fusion_r2_source_generation.py`
- `tests/unit/test_robust_fusion_r2_source_lock_v7_1.py`
- `tests/unit/test_robust_fusion_r2_source_recovery_v3.py`
- `tests/unit/test_robust_fusion_r2_source_recovery_v4.py`
- `tests/unit/test_robust_fusion_r2_source_recovery_v5.py`
- `tests/unit/test_robust_fusion_r2_source_recovery_v6.py`

### A01 · 退出新研究的默认执行身份；保留旧协议与字节，不在本轮移动或增加页头。

- `docs/plans/robust-fusion-annotation-full-guide.md`
- `docs/plans/robust-fusion-annotation-handbook.md`
- `docs/plans/robust-fusion-c2-boundary-supplement.md`
- `docs/plans/robust-fusion-engineering.md`（开始时有未提交修改）
- `docs/plans/robust-fusion-human-task-entrypoints.md`（开始时未跟踪）
- `docs/plans/robust-fusion-internal-stress-v6.md`
- `docs/plans/robust-fusion-publication.md`
- `docs/plans/robust-fusion-r1-to-r2-inheritance-matrix.md`
- `docs/plans/robust-fusion-r2-automatic-execution-v1.md`
- `docs/plans/robust-fusion-r2-gate-a-delta-checklist.md`（开始时有未提交修改）
- `docs/plans/robust-fusion-r2-human-review-finalization-v1.md`
- `docs/plans/robust-fusion-r2-research.md`
- `docs/plans/robust-fusion-r2-similarity-measurement.md`
- `docs/plans/robust-fusion-r2-source-authorship-v7-codex.md`
- `docs/plans/robust-fusion-r2-source-lock-v7-1.md`
- `docs/plans/robust-fusion-research.md`
- `docs/plans/robust-fusion-reviewer-clarifications.md`
- `docs/plans/robust-fusion-similarity-manifest.md`
- `docs/plans/robust-fusion-todo.md`（开始时有未提交修改）
- `docs/plans/研究审稿意见.md`
- `docs/plans/面向检索增强生成的多路检索融合查询级退化风险评估与策略选择.md`

### H01 · 可复用能力待拆分评估；不能因此保留全部旧流程，也不预建新框架。

- `scripts/diagnose_robust_fusion_dense_replay.py`
- `scripts/probe_robust_fusion_route_contract.py`
- `src/linkrag_eval/robust_fusion/__init__.py`
- `src/linkrag_eval/robust_fusion/replay_contract.py`
- `src/linkrag_eval/robust_fusion/similarity.py`
- `tests/unit/test_robust_fusion_replay_contract.py`
- `tests/unit/test_robust_fusion_similarity.py`

### H02 · 人工作业源码/检查器/测试/registry/HTML/symlink消费链一起审查；数据目标保护。

- `docs/plans/robust-fusion-human-task-registry.json`（开始时未跟踪）
- `docs/plans/robust-fusion-r2-adjudicator-beginner-guide.html`（开始时有未提交修改）
- `human_tasks/README.md`（开始时未跟踪）
- `human_tasks/r2-adjudication/START_HERE.html`（开始时未跟踪）
- `human_tasks/r2-adjudication/relation`（开始时未跟踪）
- `human_tasks/r2-adjudication/similarity`（开始时未跟踪）
- `scripts/check_robust_fusion_human_task_entrypoints.py`（开始时未跟踪）
- `src/linkrag_eval/robust_fusion/human_task_entrypoints.py`（开始时未跟踪）
- `tests/unit/test_robust_fusion_human_task_entrypoints.py`（开始时未跟踪）

### R01 · 后续同步活动入口与历史身份；只在CURRENT_STATUS维护进度，不把方法草案冻结。

- `README.md`
- `docs/CURRENT_STATUS.md`（开始时有未提交修改）
- `docs/DOCUMENT_CATALOG.md`
- `docs/HANDOFF.md`
- `docs/README.md`
- `docs/reports/REPORT_INDEX.md`

### R02 · 保留共享工程实现/契约/依赖，仅后续复核过时研究措辞或描述。

- `.env.eval.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `AGENTS.md`
- `docs/architecture/decoupling-plan.md`
- `pyproject.toml`
- `scripts/build_report_index.py`
- `src/linkrag_eval/judge/eval_llm.py`
- `src/linkrag_eval/llm/dense_client.py`
- `src/linkrag_eval/llm/sparse_client.py`
- `src/linkrag_eval/retrieval/recall_adapter.py`
- `src/linkrag_eval/retrieval/recall_factory.py`
- `src/linkrag_eval/store/vector_store.py`
- `tests/contract/test_ltr_v3_contract.py`
- `tests/contract/test_recall_factory.py`
- `tests/unit/test_judge_llm.py`
- `tests/unit/test_vector_store.py`
- `uv.lock`
<!-- GENERATED-INVENTORY-END -->
