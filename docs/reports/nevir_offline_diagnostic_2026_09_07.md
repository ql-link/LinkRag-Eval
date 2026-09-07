# NevIR 开发材料离线诊断：legacy 与英文适配版重放

日期：2026-09-07。类型：已有开发材料的描述性诊断；不属于新方法效果实验或独立确认。

**阅读入口：§1–6 保留原 legacy A/B 诊断，§7 是随后按负责人要求完成的原 A／英文适配版重跑。当前两个模型的身份见[模型入口](../../models/README.md)。**

**原 legacy 诊断当时的决策：暂不改动。** 全部开发输入、原 38 维及 A/B 树路径已经实际重放，未发现计算不一致。当前能确认一些特征没有响应，以及模型如何落到相同或不同叶节点；尚没有两名人类独立复核及裁定，不能把这些现象认定为造成可靠语义错误的因素。因此本轮完成机械诊断与盲审材料，可靠语义归因保持待审。

## 1. 输入及执行范围

使用当前工作区 `/Users/kawauso/Documents/Projects/LinkRag-Eval`，分支 `feat/nevir-ltr-validation`，HEAD `af6267d69cb9a4aeb194bf6c49eb589df8912bac`，包含此前未提交 A/B 实现及本轮新增离线模块。本轮不 commit/push，不更换分支或覆盖原结果。输入位置、相关未提交路径、本地版本和要求的模型／开发快照哈希见 [manifest](../../runs/post_recall/nevir-offline-diagnostic-20260907/manifest.json)。

| 核对项 | 实际结果 |
| --- | --- |
| 冻结 A | `candidate-difference-v3-20260728-final33`，33 棵树 |
| 重训 B | `nevir-ltr-same38-20260907-b`，51 棵树；保留此前选出的模型 |
| 原计算契约 | `candidate_difference_v3`，原顺序 38 列，实际输入 `float32` |
| 本地运行环境 | Python 3.11.15、NumPy 2.4.6、LightGBM 4.7.0；预测显式单线程 |
| 开发总体 | 76 查询、38 配对、19 来源组，全部保留 |
| 完整候选并集 | 合计 10,465 条查询—候选记录 |
| 指定两段共同覆盖 | 74 查询、37 个双向覆盖配对 |
| 覆盖限制 | 2 查询缺目标，共缺 3 个目标槽位；不记排序错误，也不补入模型输入 |

模型包的五个文件校验和各自三条已有合成契约向量均通过；契约向量验证特征／次序，不冒称其带有历史原始分数。A 的 Booster 列名为 `Column_0…37`，依据这个已冻结旧包的显式位置契约核对；B 的列名与 38 列名称逐项一致。

模型输入始终先按完整保存池计算，再提取指定两行用于诊断。缺失查询中，一条两段均未覆盖，另一条仅覆盖官方 preferred 段，因此全量 152 个目标槽位实际在场 149 个。正文、身份、三路分数、路内次序及状态沿用开发快照；原函数按列表位置构造内部排名，因此删池后重编号不能冒充保留原排名的探针。其他角色可能共享的正文仅作为开发池正文使用，没有读取确认或 Test 的查询、标签、逐题表现。未触发训练支持检查，未读 Train 实例。

## 2. 重放和逐树核验

历史只提供了本轮使用的 B 开发逐候选分数。10,465 条 B 分数精确一致，逐题来源组、配对、方向、标签状态、候选数、严格偏好及原始分差也一致。A 为本轮重新计算，未声称存在 A 历史开发分数的逐值对照。

追踪前后，全池 ID、38 维矩阵和 A/B 分数精确不变。每个共同覆盖查询分别核对 A/B 的全部树，合计 **6,216 条树级成对记录、12,432 条目标路径**。叶节点同时与 `pred_leaf`、模型 dump 和 `get_leaf_output` 核对；不重复乘 shrinkage，不将两模型同序号树当成对应结构。

| 数值验收 | 结果 |
| --- | --- |
| 原始分数重建最大绝对误差 | 0 |
| 成对分差重建最大绝对误差 | `3.8163916471489756e-16` |
| 预先规定的重建容差 | `atol=1e-10, rtol=0` |
| 偏好／同分判断 | 原始浮点数直接 `>`、`<`、`==`；不使用上述容差 |

详细证据见 [replay-check.json](../../runs/post_recall/nevir-offline-diagnostic-20260907/replay-check.json) 和 [tree-audit.jsonl](../../runs/post_recall/nevir-offline-diagnostic-20260907/tree-audit.jsonl)。本轮只计算纯模型分数；未调用在线短查询／超时回退，也不以 ID 排序打破模型原始分数同分。模型包中原在线策略另存于 manifest，未修改。

## 3. 全量开发结果及机械观察

以下只按官方偏好计数，不能写成已经人工确认的错误数。开发材料参与过 B 选模，这组收益不能用作新独立证据。

| 原始模型结果 | A | B |
| --- | ---: | ---: |
| 严格符合官方偏好 | 38/74 | 47/74 |
| 严格逆序 | 35/74 | 27/74 |
| 同分 | 1/74 | 0/74 |
| 双向均严格符合 | 6/37 | 11/37 |

四格为：双方严格符合 **27**，仅 B 符合 **20**，仅 A 符合 **11**，双方未严格符合 **16**。纠正 20、改坏 11，净增 9；这些是开发集数字，不与此前确认集的 58／50 合并。全部四格与两个覆盖限制实例均有追踪索引；来源组分布见 [summary.json](../../runs/post_recall/nevir-offline-diagnostic-20260907/summary.json)，逐例见 [diagnosis.md](../../runs/post_recall/nevir-offline-diagnostic-20260907/diagnosis.md) 和 [cases.jsonl](../../runs/post_recall/nevir-offline-diagnostic-20260907/cases.jsonl)。

**完整 38 维精确碰撞为 0/74。** A 有一条查询的两段在全部树中落到相同叶节点，产生该模型唯一的同分；B 没有这样的查询。因此，不能用“这批目标的完整向量完全相同”解释严格逆序；没有完整碰撞也不能证明表示充分。

**四列在全部 10,465 行上恒为零：** `negation_overlap_coverage`、`negation_mismatch`、`same_doc_candidate_count`、`same_doc_max_bigram_similarity`。现有否定字典由中文词组成，同文档列依赖合法 doc_id 分组。这批数据没有激活这些列，可以确认它们没有提供变化信号；不能直接推出补英文否定词或人为把官方配对设为同文档便会改善结果。官方配对不是合法输入特征。

字符 n-gram 在规范化后取集合，覆盖率合并不同位置的命中。追踪保存去重前的出现次数、原文位置、实际分句和去重后统计；新记录的诊断句子位置没有进入模型。上述处理方式是代码事实，**哪一次合并丢失了决定适用性的关系仍待复核**。数值不同不等于已经编码了正确关系，局部统计相同不等于整行输入相同。

三路与冻结加权融合的方向也已保存。下表分母均为全部 76 查询，“缺目标”指该路或并集没有共同覆盖；不能直接横比不相同可评子集的准确率。

| 输出 | 严格符合 | 严格逆序 | 同分 | 缺目标 |
| --- | ---: | ---: | ---: | ---: |
| Dense 原始分数 | 39 | 32 | 0 | 5 |
| Sparse 原始分数 | 23 | 26 | 0 | 27 |
| BM25 原始分数 | 28 | 32 | 10 | 6 |
| 冻结加权融合分数 | 38 | 36 | 0 | 2 |

这回答了“原路是否已经存在不同偏好、目标是否在场”，没有单凭路间方向认定召回器或排序器理解了必要条件。两条配套查询的实际候选池可能不同，不能当成只改变 query 的受控干预。未计算全池 nDCG、自然错误率或新增显著性区间。

## 4. 人工材料、未执行项与单一决策

未取得两名人类审阅者的独立提交或裁定；此前的 AI 分析和曝光标记保留原身份。本轮没有生成 AI 暂定标签。全部 76 查询的语义类别为 `unknown_pending_human_review`，覆盖 38 配对、19 来源组；不伪造提取缺口、聚合丢失或相关编码的语义类别占比。

两套材料均包含全部 76 个匿名案例，每例查询和两段全文，各自独立打乱；公共文件不含官方方向、模型分数／排名、来源组、配套 query ID 或另一人意见。缺目标查询也保留，两段正文都可从已有开发池取得；模型输入保持原缺失状态。姓名与审阅者类型由填写者明确选择，证据用逐字摘录和 Unicode 位置，另有成对偏好和歧义字段，不强迫一正一负。映射保存在 `review/private/`，不要交给审阅者。

- [审阅者 1 页面](../../runs/post_recall/nevir-offline-diagnostic-20260907/review/reviewer_1/review.html)
- [审阅者 2 页面](../../runs/post_recall/nevir-offline-diagnostic-20260907/review/reviewer_2/review.html)
- [材料说明](../../runs/post_recall/nevir-offline-diagnostic-20260907/review/README.md)：也可使用各目录的 `cases.jsonl` 和 `blank-answers.jsonl`。

本轮未选择某种文本编辑或删池探针，未检查训练支持，分别记录 [probe_plan.json](../../runs/post_recall/nevir-offline-diagnostic-20260907/probe_plan.json) 与 [training-support.json](../../runs/post_recall/nevir-offline-diagnostic-20260907/training-support.json) 为 `not_run`。执行说明允许无可靠假设时不运行探针；常量列和路径差异尚不足以选定一个因果解释。

**唯一下一步决策是暂不改动算法。** 先接收两份独立盲审并裁定分歧，再与现有追踪关联。推翻该决定需要在不同来源的可判实例中，将一项具体处理、聚合或模型利用缺口连接到可靠错误，同时检查原正确及不支持该机制的例子，足以提出一项可单独检验的变化。详见 [decision.md](../../runs/post_recall/nevir-offline-diagnostic-20260907/decision.md)。这不是宣称 38 维足够、局部信息无用或研究应结束。

## 5. 工程交付与复现

新增三个离线模块：[编排与盲审材料](../../src/linkrag_eval/retrieval/learning_to_rank/nevir_diagnostics.py)、[特征旁路追踪](../../src/linkrag_eval/retrieval/learning_to_rank/diagnostic_features.py)、[逐树审计](../../src/linkrag_eval/retrieval/learning_to_rank/diagnostic_trees.py)，各有定向单元测试。原特征核心和模型未改。新入口遇到关键输入缺失、历史 B 关联／分数不一致或重建不一致会保留准确阻断记录，停止依赖解释。

正式诊断一次执行，退出码 0，命令外层耗时约 8.18 秒；这是本地批量诊断时长，不是线上延迟或训练成本。原始命令、stdout 和 stderr 见 [execution-log.txt](../../runs/post_recall/nevir-offline-diagnostic-20260907/execution-log.txt)。复现时必须选一个新的输出目录：

```bash
.venv/bin/python -m linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics \
  --experiment-dir runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment \
  --model-a models/candidate-difference-v3-20260728-final33 \
  --model-b runs/post_recall/nevir-ltr-validation-20260907/training-preparation/training/model-b \
  --saved-b-predictions runs/post_recall/nevir-ltr-validation-20260907/training-preparation/training/dev-predictions.jsonl \
  --execution-plan runs/post_recall/nevir-offline-diagnostic-20260907/execution-plan.md \
  --out runs/post_recall/nevir-offline-diagnostic-NEW
```

大产物留在 Git 忽略的 [运行目录](../../runs/post_recall/nevir-offline-diagnostic-20260907/)，包括约 156 MB 的特征追踪、16 MB 的树路径、全池矩阵和原始分数；不会随 clone 自动出现。根目录的一次性交接包在说明留档、重复报告与现有原报告核对一致后删除；可持续维护的边界已归入[研究计划 §2.4](../plans/post-recall-research-plan.md#24-开发材料上的离线机制诊断)，没有新建重复计划入口。

机械状态 `completed`，人工状态 `pending`，综合状态 `partially_completed`。没有关键输入或重放技术阻断。浏览器安全策略拒绝本地 `file:` 页面预览，因此不声称已完成视觉验收；公共材料的结构、内容隔离和表单脚本另作自动检查。最终代码检查及独立产物验收记录见下节。

## 6. 最终验收

本轮重新运行 `LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/pytest -m 'not integration' -q`，结果 **953 passed、3 deselected**，6 条依赖弃用警告，退出码 0；含真实生产依赖的离线契约及导入边界检查。见[完整日志](../../runs/post_recall/nevir-offline-diagnostic-20260907/final-nonintegration-tests.log)与[命令回执](../../runs/post_recall/nevir-offline-diagnostic-20260907/test-execution.json)。本轮新增 72 项诊断测试覆盖规范化位置、池统计、float32 对齐、缺失值分支、逐树重建、历史 B 错配阻断及盲审隐私；它们属于上述 953 项，不另行相加。

三个新增模块及三个测试文件的 Ruff、报告索引和 `git diff --check` 通过；本轮涉及的六份入口／报告文档中的本地文件链接全部可解析。盲审表单的 JavaScript 在本机 Node 的合成 DOM 中验证缓存隔离、身份恢复、当前题导出及 Unicode 证据位置，发现并修复结束位置越界后重跑通过；没有浏览器渲染验收，也没有产生人工标签。

独立只读[验收结果](../../runs/post_recall/nevir-offline-diagnostic-20260907/independent-acceptance.json)为 **passed**，[验收脚本](../../runs/post_recall/nevir-offline-diagnostic-20260907/independent_acceptance.py)直接核对已保存产物，未重新预测。76 组案例／预测／追踪、74 组树审计、全部 10,465 行矩阵、149 个在场目标槽位、6,216 条树级记录及 12,432 条路径一致；B 历史分数、次序、关联元数据，统计汇总及两份公共盲审的文本／隐私边界均通过。独立验收脚本初次误假定缺失槽位为 2，修正为按真实并集计算后通过；该次脚本失败另留回执，没有为满足假定修改原产物。


## 7. 英文适配版在同一快照上的重跑（2026-09-07）

**机械诊断重跑通过。两列英文否定特征恢复响应，两列同文档特征仍全零；而在 74 条可评价查询的指定候选对中，否定重叠列全部相同，否定不匹配列仅 5 对不同。** 这将问题从“没有识别英文否定词”收窄到“当前词面集合统计能否区分指定近似候选”。后者尚无人工语义裁定，不能直接认定否定范围是已证实的错误成因。

### 7.1 范围与模型绑定

负责人要求重跑 §2.4 的既有机械诊断，范围维护在[研究计划 §2.6](../plans/post-recall-research-plan.md#26-英文适配模型在原开发快照上的诊断重放)。仍用原 **76 查询／38 配对／19 来源组、10,465 候选行**的开发快照，指定目标共同覆盖 **74 查询／37 配对**。这批材料曾参与英文模型早停选轮，虽然讨论中称为“英文测试集”，严格说是开发材料，不能当作新的独立测试。

本次仅加载最初 A（33 棵树、legacy `candidate_difference_v3`）及已保存英文适配模型（67 棵树、`candidate_difference_v3_en_v1`／`english_basic_v1`）。各自计算并追踪绑定版本的完整矩阵，不能把英文权重直接套在旧词表矩阵上。原 B 只保留历史结果，本次不加载或重训。未更换分支、commit/push、调用外部模型或召回；没有改变正文、候选、模型权重、特征规则、标签或阈值。只读取开发逐题及模型训练元数据，没有读取 Train、确认或 Test 的查询正文、标签和逐题表现。

### 7.2 四列的全池响应

下表中零／非零均以相同 10,465 个查询—候选行为分母。旧 A 的四列统计精确复现旧诊断；英文值也与上轮训练时保存的开发矩阵精确一致。

| 特征 | 原 legacy 非零行 | 英文非零行 | 英文零行 | 英文实际取值 |
| --- | ---: | ---: | ---: | --- |
| `negation_overlap_coverage` | 0 | 1,623 | 8,842 | 0、1 |
| `negation_mismatch` | 0 | 5,459 | 5,006 | 0、1 |
| `same_doc_candidate_count` | 0 | 0 | 10,465 | 0 |
| `same_doc_max_bigram_similarity` | 0 | 0 | 10,465 | 0 |

**词表怀疑对两列否定特征成立。** 原词表没有英文否定条目，新规则识别基本否定词与缩写后出现上述响应；76 条查询中 26 条有规则识别出的否定词。这里的“识别”只指词面规则，不是理解否定对象或范围。

**同文档列的零值由当前输入的文档分组决定。** 本次逐池核对发现，76 个池中的每个 `doc_id` 分组均只有一个候选，因此没有同文档同伴可计数或比较。此现象不依赖英文词表；本次没有用官方配对关系伪造文档身份。

### 7.3 有响应不等于能分清指定候选

每一项“对”指某一查询下指定的 preferred／other 两段；分母是 74 条共同覆盖查询，不是 74 个独立来源或 74 个 NevIR 双向样本。

| 英文特征 | 两段值相同 | 两段值不同 | 两段都为零 | 两段都非零 |
| --- | ---: | ---: | ---: | ---: |
| 否定重叠覆盖 | 74 | 0 | 65 | 9 |
| 否定不匹配 | 69 | 5 | 33 | 36 |
| 同文档候选数 | 74 | 0 | 74 | 0 |
| 同文档最大 bigram 相似度 | 74 | 0 | 74 | 0 |

否定重叠列虽在全池 1,623 行非零，却不能凭该列直接区分本批任何一个指定候选对。这不等于该列对整池排序或树的后续分支没有作用。完整 38 维在 A／英文两种表示下均为 **0/74 精确碰撞**，说明其他列仍有差异；不能由某一列相同推导整套表示相同或充分。

### 7.4 模型是否真正使用了这些列

| 特征 | A 模型分裂结点数 | 英文模型分裂结点数 | 英文目标路径遇到该列的查询数／74 | 在共同结点上因该列分向不同分支的查询数 |
| --- | ---: | ---: | ---: | ---: |
| 否定重叠覆盖 | 0 | 24 | 74 | 0 |
| 否定不匹配 | 5 | 1 | 45 | 2 |
| 同文档候选数 | 13 | 0 | 0 | 0 |
| 同文档最大 bigram 相似度 | 18 | 0 | 0 | 0 |

英文模型使用了否定列，不能说它完全忽略新词表产生的信号。但“模型有分裂”“路径经过某列”“两个目标在该列分叉”是三种不同机械观察。上述分裂次数不是特征的语义贡献，也不证明纠正了某种可靠语义错误。全部 **7,400 条树级成对记录／14,800 条目标路径**已核对 `pred_leaf`、dump 和 `get_leaf_output`；A／英文各有 1 条全部树同叶的查询，对应各自的 1 条同分。

### 7.5 重放结果与解释边界

| 官方偏好口径 | 最初 A | 英文适配版 |
| --- | ---: | ---: |
| 严格正确 | 38/74 | 44/74 |
| 逆序 | 35 | 29 |
| 同分 | 1 | 1 |
| 双向全对 | 6/37 | 9/37 |

四格：共同正确 **26**、仅英文正确 **18**、仅 A 正确 **12**、共同未严格正确 **18**；另有 2 条缺目标保留且不记错排。来源分布见 [summary](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/summary.json)。这里原 A→英文净增 6 同时包含训练适配与规则差异，不能直接说“英文词表带来 6 条提升”。此前[同条件重训比较](nevir_english_features_2026_09_07.md)仍是 legacy 控制 47/74、英文 44/74；本次英文逐候选分数、排序和偏好与其保存产物精确一致，负结果没有改变。

**后续只建议完成现有盲审，核对这些取值相同的指定候选之间，可靠区别究竟是什么。** 可检验的机械线索是“粗粒度否定统计通常不能区分指定对”，具体是否需要范围／对象或其他关系信息仍待审。本次没有新增词表、局部窗口、模型、门控、训练支持检索或干预探针。

### 7.6 实现、验收和实际产物

在原 `diagnostic_features.py` 增加显式英文追踪分派，只恢复中间态与原文位置，数值仍来自冻结特征核心；原统计汇总允许明确的 A／English 模型名称。一次性[英文诊断入口](../../scripts/nevir_english_diagnostics.py)复用现有输入校验、追踪、树审计和盲审材料生成。评分核心 `features.py`、`english_rules.py`、`online.py`、模型包及训练入口均未因这轮重跑修改。

- 原 A 的矩阵、全候选分数及 **76 条原追踪完整内容精确一致**；英文矩阵和全候选分数与上轮保存产物精确一致。trace 开／关均不改变任何矩阵或分数。
- 树分数重建最大误差 **0**，分差重建最大误差 **3.8163916471489756e-16**；沿用 `atol=1e-10, rtol=0`，仅用于工程重建，同分仍精确判断。
- 普通英文追踪新增大小写、撇号、词边界、小数、编号、缩写和分句原文位置样例；错配 legacy 矩阵时拒绝解释。保存分数的身份、背景候选、分数、方向、次序损坏测试均明确阻断。
- 完整回归命令 `LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/pytest -m 'not integration' -q`：**1,047 passed、3 deselected、6 warnings**，见[日志](../../runs/post_recall/nevir-english-diagnostic-20260907/checks/tests-after-diagnostic-changes.log)；本次修改模块及新脚本／测试 Ruff 通过。CLI `--help`、报告索引、文档链接和 `git diff --check` 已检查；原有未提交改动保留。
- 实际诊断一次，退出 0，入口内部 **15.14 秒**、进程外层 **15.73 秒**，无新拟合或远端调用。此耗时包含追踪和文件输出，不是线上预测延迟。
- 两套各 76 题盲审材料正常生成，公共案例与上轮逐字节相同，原材料仍可沿用；人类提交 0、AI 标签生成 0。综合状态 `partially_completed` 仅表示人工层待审，机械状态为 `completed`，无技术阻断。

产物入口：[运行 manifest](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/manifest.json)、[实际命令与耗时](../../runs/post_recall/nevir-english-diagnostic-20260907/execution.json)、[全量统计](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/summary.json)、[逐题结果](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/cases.jsonl)、[重放验收](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/replay-check.json)、[保存产物独立算术复核](../../runs/post_recall/nevir-english-diagnostic-20260907/artifact-verification.json)、[盲审说明](../../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/review/README.md)。

A／英文的矩阵与全文中间态分别在 `diagnostic/A/` 和 `diagnostic/English/`；树路径在 `diagnostic/tree-audit.jsonl`，全池原始分数在 `diagnostic/raw-predictions.jsonl`。所有大产物保存在本轮独立 `runs/` 目录，旧诊断、旧模型和训练结果原位保留。
