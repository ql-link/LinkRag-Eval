# NevIR 基础英文特征隔离与受控重训报告

> 日期：2026-09-07。分支 `feat/nevir-ltr-validation`，HEAD `af6267d69cb9a4aeb194bf6c49eb589df8912bac`，本地未提交状态；本轮未切分支、commit 或 push。范围依[研究计划 §2.5](../plans/post-recall-research-plan.md#25-基础英文版本与同条件开发比较)，历史事实分别见[同 38 维重训报告](nevir_same38_retraining_2026_09_07.md)与[离线诊断报告](nevir_offline_diagnostic_2026_09_07.md)。

**技术验收通过，开发效果没有提高。** 独立结构阶段保持旧行为，英文基础处理有明确版本与测试。legacy 控制组的模型权重、开发全候选分数和排序精确复现原 B；英文组严格正确从 47/74 降至 44/74（−4.05 个百分点），纠正 5、改坏 8，双向全对 11/37→9/37。两组各拟合一次，没有后续调参或追加规则。此结果只说明本轮五列基础处理的整体适配没有带来开发净收益，不能单独归因到某一修复，不能证明特征空间上限。

## 1. 实际文件结构与行为不变阶段

先核对当前源码、原 A/B 包及 Train／开发实体，记录[初始状态](../../runs/post_recall/nevir-english-features-20260907/initial-state.json)和[原有跟踪改动](../../runs/post_recall/nevir-english-features-20260907/initial-tracked.diff)，不把历史报告当作文件清单。实际整理如下，未移动历史模型、候选、实验目录或结果。

| 原位置／职责 | 保留或调整 | 原因 |
| --- | --- | --- |
| `learning_to_rank/experiment.py` 同时含特征、带标签包装、CV／报告 | 将常量和 9 个无标签计算函数原样提取到同目录 `features.py`；带标签包装与历史实验保留，现有公开导出仍可用 | 在线、训练和诊断共用计算，不依赖实验编排 |
| `online.py` 模型包、预测、运行策略 | 保留位置；在后续实现阶段补版本契约 | 已有职责合理 |
| `cache.py` 原始召回缓存 | 保留；本轮没有特征矩阵缓存读取 | 原始候选不等于可跨版本读取的矩阵 |
| `pairwise_training.py`、`nevir_evaluation.py`、三个诊断模块 | 保留；核心引用改到 `features.py`，单配置选择扩展留在训练模块 | 复用原训练／评价；旧诊断仍明确为 legacy |
| 一次性两组实验编排 | 新增 `scripts/nevir_compare_feature_versions.py`，调用同一核心 | 本轮路径核对和比较不进入在线排序器 |
| 英文差异规则 | 新增同目录 `english_rules.py` | 共用框架，只分派必要规则；没有复制整套 LTR |
| `tests/unit/` | 新增英文规则／比较编排测试，扩展已有导出／训练测试 | 与被测职责对应 |
| `docs/plans/post-recall-research-plan.md` | 继续维护唯一设计入口；本任务仅新增本报告 | 不在根目录建立平行计划 |
| `models/`、`runs/post_recall/` | 原 A/B 不动，新模型、矩阵、日志放本轮 `runs/` 子目录 | 大产物不进源码；旧实验不覆盖 |

阶段一先运行原测试，**953 passed、3 deselected**；纯结构整理后仍是 **953 passed、3 deselected**。9 个提取函数的 AST 与整理前一致。同环境重放 76 条历史英文开发输入＋3 条既有中文契约输入，共 10,473 候选行，特征 float32、A/B 原始分数和排序全部精确相等；历史开发快照的冻结数值检查也保留。未调整容差或同分判据。英文实施前已单独通过[结构验收](../../runs/post_recall/nevir-english-features-20260907/stage1-acceptance.json)，实施后[legacy 重放](../../runs/post_recall/nevir-english-features-20260907/legacy-final-replay.json)仍通过。

## 2. 基础英文审查与修改

以下规则在看到新版本 NevIR 分数前，以普通样例确定；不是新方法效果证据。[原行为最小复现](../../runs/post_recall/nevir-english-features-20260907/english-rule-audit-before.json)留档。

| 检查项 | 旧行为 | 最小复现 | 需要修改 | 修改范围 |
| --- | --- | --- | --- | --- |
| 基本否定与缩写 | 否定词表只有中文项目，英文集合为空 | `not`、`cannot`、`isn't` | 是 | 英文版识别 not/no/never/neither/nor/without 和 20 个明确的否定缩写；cannot／这些缩写归一为 not |
| 否定大小写与撇号 | 英文否定本身未接入；字符 n-gram 已大小写等价、可清除撇号 | `ISN'T`、`isn’t`、`isn‘t`、`ISNʼT` | 仅补英文否定 | 词表大小写不敏感，三种 Unicode 撇号统一；n-gram 不改 |
| 否定词边界 | 没有可用英文否定匹配 | `not` 对照 `notable`、`knot`、`not2`、`not_a_token` | 是，随新词表 | 单词边界限制，禁止词中子串误命中；hardly/barely 不擅自补入 |
| 英文分句 | 不按英文句点或 and/but/if 分句 | `Alpha ready. Beta ready.`、`candy butter gift` | 是 | 英文版增加句点及有词边界的三个连接词；保留原标点规则与覆盖阈值 |
| 小数／缩写句点 | 旧版不按英文句点切，原本没有小数句点误切；新分句需保护 | `Dr. Lee paid 3.14.`、`U.S.`、`e.g.`、`J. Smith` | 配套保护 | 数字中间句点、有限常见缩写和姓名首字母保护；不是完整句法解析 |
| 千分位逗号 | 被当分句符，数字切成两部分 | `Count 1,234.50.` | 是 | 保护合法千分位标点，提取为 `1234.50`，不解析单位、负号语义或财报关系 |
| 数字精确匹配 | 查询提取后在正文做子串覆盖 | `3.14` 在 `13.14` 中误计为覆盖；`12` 对 `123` 同样 | 是 | 在两边提取数字集合后精确比较；日期等仍按既有基础抽取意图处理 |
| 编号标点与精确匹配 | 吞入句末标点／正文子串匹配 | `ABC-12.` 对 `ABC-12 is ready.` 漏匹配；`ABC-12` 对 `ABC-123` 误匹配 | 是 | 复用已有抽取模式，剥离尾部 `._-`，保留内部版本／编号标点，比较提取集合 |
| 字符 n-gram、大小写、长度、查询含数字 | 既有实现能处理相应普通英文输入；字符级是原设计 | `ISN'T` 与 `isn’t`、`v2.1` 与 `V2.1` | 否 | 不改字符级设计或其余公式 |
| 同文档两列 | 匿名接入每段不同文档，原诊断恒零 | 当前保存候选元数据 | 否 | 不用官方配对伪造同文档关系 |

只影响 `identifier_exact_coverage`、`number_exact_coverage`、`negation_overlap_coverage`、`negation_mismatch`、`condition_coverage` 五列；维度与列序仍是 38，其余 33 列在全部 Train／开发候选上精确一致。分句覆盖仍用字符 bigram 集合的原 0.5 阈值。**词面否定识别不等于理解否定的是谁**；缩写保护可能保守地漏掉缩写后的句边界，数字规则也不承担数值推理或完整实体识别。

## 3. 版本、模型及缓存隔离

| 项目 | legacy | 英文 |
| --- | --- | --- |
| 特征版本 | `candidate_difference_v3`，原默认 | `candidate_difference_v3_en_v1`，必须显式选择 |
| 规则版本 | `legacy_v3`；原包可无新增字段，但须明确旧契约 | `english_basic_v1`，新包必须具备 |
| 列序 | 原 38 列 | 同一 38 列，不能仅因维数相同而混用 |
| 训练选择 | 旧默认六配置保持；本轮显式 c3 | 要求显式版本＋单个配置，本轮 c3 |
| 模型加载 | 原 A/B 默认路径不变 | `LambdaMartOnlineRanker(path, feature_version="candidate_difference_v3_en_v1")` |

特征签名绑定版本和列序，英文签名还绑定规则版本；manifest 与 feature_contract 相互校验，实际 Booster 列名和树数也校验。旧 A 的位置列名仅在已核实模型版本及文件校验值匹配时兼容；未知包不因 38 列就猜成 legacy。缺失特征版本、未知规则、请求／模型或矩阵／模型版本错配均拒绝，明确的版本错配不会静默回退。新增包还保存原始分数契约，重载后全开发预测精确一致。冻结 A/B 包没有回写新增字段。

输入与矩阵分开：原始快照复用，两个版本每次从全池重新计算。数据对象携带版本，Train／开发版本不同在拟合前报错；原始输入中即使出现未经信任的 `features` 字段也不会成为矩阵输入。本轮两份开发 NPZ 名称及其所属模型记录均区分版本，**它们是输出，不存在读取旧 NPZ 的缓存入口**。不构建通用插件框架或复杂多语言平台。

## 4. 一次受控重训的输入与规则

六个输入路径逐一与旧 B 的 `selection.json` 核对，只读保存 Train／开发，不读取确认／Test 逐题、调用采集或外部模型。两组完整候选、列序、指定目标索引、标签、权重与排除项核对一致；仅五列允许不同。

- Train 1,896 查询／948 配对，原计划 473 来源；共同覆盖 1,871，排除两条原结构冲突方向，**1,869 查询／472 来源、3,738 行进入损失**。25 条缺目标，全部查询仍有已保存全池输入。
- 开发总体 76 查询／38 配对／19 来源；共同覆盖 **74 查询／37 完整配对**，2 条缺目标不补入，不从总体消失。
- 全池特征计算覆盖 Train **269,941** 和开发 **10,465** 个查询—候选行；先全池计算，再取合法两段监督。未判断背景不作负例。
- 权重沿用 `N_queries / (N_sources × queries_in_source)`，同一查询的两行等权；来源隔离、查询顺序及结构冲突排除与旧记录一致。

原 B 选中的 **c3** 固定：num_leaves=7、max_depth=3、reg_lambda=1、learning_rate=0.03、colsample_bytree=0.8、种子 20260907、最大 300 轮、40 轮早停、单训练线程及原确定性参数。所有参数与原记录逐字段相等，未扩大网格。早停依据仍是来源宏平均严格单查询正确率，取首次最佳轮；导出该树前缀，无 refit。具体完整参数在[两组配置与结果](../../runs/post_recall/nevir-english-features-20260907/comparison/comparison.json)。环境与旧 B 同为 Python 3.11.15、LightGBM 4.7.0、NumPy 2.4.6、scikit-learn 1.9.0。

| 训练记录 | legacy 控制 | 英文适配 |
| --- | ---: | ---: |
| 实际拟合次数 | 1 | 1 |
| 选中／保存树数 | 51 | 67 |
| 实际评估轮数（含早停等待） | 91 | 107 |
| 停止原因 | early_stopping | early_stopping |

两组遵守同一选轮规则，实际轮数不同。legacy 模型 `model.txt` 字节及全部开发预测 JSONL（分数、顺序、关联）与原 B 完全相同后才启动英文拟合。没有将环境差异记作英文收益。本比较使用纯模型全池分数；模型包沿用的短查询／超时回退没有参与这组效果指标，未改变 active registry。

## 5. 开发集实际结果与响应

严格正确要求指定优选段落原始分数严格大于另一段，逆序小于，同分精确相等；无 epsilon 改判或 ID 破同分。官方标签原样报告。

| 指标 | 原 A（历史诊断参照） | 原 B＝本轮 legacy | 本轮英文 |
| --- | ---: | ---: | ---: |
| 严格正确 | 38/74（51.35%） | 47/74（63.51%） | 44/74（59.46%） |
| 逆序 | 35 | 27 | 29 |
| 同分 | 1 | 0 | 1 |
| 双向全对 | 6/37 | 11/37（29.73%） | 9/37（24.32%） |
| 来源宏平均严格正确率 | — | 64.47% | 60.53% |

英文相对 legacy：**共同正确 39、纠正 5、改坏 8、共同未严格正确 22**；另有 2 条共同不可评价。净减 3 条、−4.05 个百分点；双向全对减少 2 对。13 条严格正确状态发生切换，不能把这组结果说成“没有影响”。来源宏平均下降 3.95 个百分点。来源净增为正 2 组、负 4 组、净值为零 13 组；净零可以包含组内抵消。

| 来源后缀（均为 nevir-validation） | 共同正确 | 纠正 | 改坏 | 共同未正确 | 缺目标 | 净增 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0462 | 2 | 0 | 2 | 0 | 0 | -2 |
| 0468 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0471 | 1 | 1 | 1 | 1 | 0 | +0 |
| 0473 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0475 | 2 | 1 | 0 | 1 | 0 | +1 |
| 0476 | 1 | 0 | 2 | 1 | 0 | -2 |
| 0478 | 2 | 2 | 0 | 0 | 0 | +2 |
| 0479 | 2 | 0 | 1 | 1 | 0 | -1 |
| 0494 | 1 | 1 | 1 | 1 | 0 | +0 |
| 0504 | 3 | 0 | 0 | 1 | 0 | +0 |
| 0508 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0516 | 3 | 0 | 0 | 1 | 0 | +0 |
| 0518 | 2 | 0 | 1 | 1 | 0 | -1 |
| 0533 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0548 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0557 | 2 | 0 | 0 | 0 | 2 | +0 |
| 0558 | 2 | 0 | 0 | 2 | 0 | +0 |
| 0561 | 3 | 0 | 0 | 1 | 0 | +0 |
| 0564 | 3 | 0 | 0 | 1 | 0 | +0 |

各修改列实际响应如下。“变动候选／查询”是新旧矩阵值不同的数量；不是语义改善数量，计算范围含缺目标查询的真实候选池。

| 特征列 | Train 变动候选／查询 | 开发变动候选／查询 | 开发非零候选数 legacy→英文 |
| --- | ---: | ---: | ---: |
| `identifier_exact_coverage` | 66 / 8 | 6 / 2 | 24 → 18 |
| `number_exact_coverage` | 1,028 / 44 | 0 / 0 | 24 → 24 |
| `negation_overlap_coverage` | 41,915 / 603 | 1,623 / 26 | 0 → 1,623 |
| `negation_mismatch` | 138,418 / 1896 | 5,459 / 76 | 0 → 5,459 |
| `condition_coverage` | 22,347 / 171 | 923 / 5 | 747 → 1,670 |

数字覆盖列在开发本身未变，但训练侧发生变化，不能因此从这一整体适配中排除其训练影响。两列同文档特征仍为零且未改；其他 33 列全部一致。否定列从零变为有响应，只证明新规则被执行，不证明捕获了正确否定范围。没有新的人类复核结果；已有盲审材料仍待提交，不将 AI 判断或官方偏好直接包装成人工金标。

## 6. 成本、测试与验收

本地 CPU、实际预测单线程；单位均为秒。各项有包含关系，不能相加当总耗时。按 legacy→英文顺序测一次，未做稳定延迟基准或置信区间。

| 计时范围 | legacy | 英文 |
| --- | ---: | ---: |
| Train 全池特征 | 30.627163 | 44.335898 |
| 开发全池特征 | 1.195847 | 1.704561 |
| 读取＋准备两划分 | 33.389860 | 48.074651 |
| 拟合＋树前缀＋开发指定对检查 | 0.076179 | 0.072390 |
| 训练编排＋导出＋全池预测 | 0.930140 | 0.968582 |
| 开发 76 池预测＋排序＋记录 | 0.008823 | 0.009726 |

特征计时只包围 `build_online_features`，包含全池字符集合及新英文规则；读取＋准备另含 JSON 读取、验证和监督选取，英文项还含新旧全池对账。拟合项含工作进程内 LightGBM 拟合、树前缀转换、指定对开发算分；训练编排项另含进程启动、导出和全池预测。开发预测项包含 76 次 Booster 调用、排序和记录组织，不含特征、模型加载或磁盘写入。两组完整命令墙钟 **84.33 秒**；新英文开发特征约 1.70 秒，legacy 约 1.20 秒。本轮没有外部模型／编码／召回成本，不将这一次计时外推为线上 SLA。

| 检查 | 命令／证据 | 实际结果 |
| --- | --- | --- |
| 初始测试／结构阶段 | `LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/pytest -m 'not integration' -q`；[初始日志](../../runs/post_recall/nevir-english-features-20260907/checks/tests-before-changes.log)、[结构日志](../../runs/post_recall/nevir-english-features-20260907/checks/tests-after-structure-full.log) | 各 953 passed、3 deselected；既存警告 6 |
| legacy 冻结契约与同环境重放 | `.venv/bin/python runs/post_recall/nevir-english-features-20260907/legacy_replay.py legacy-final`；[结果](../../runs/post_recall/nevir-english-features-20260907/legacy-final-replay.json) | 79 输入、特征／A/B 分数／排序精确一致，A/B 各 5 文件与 3 契约向量通过 |
| 英文正反例／模型隔离／缓存来源／单配置编排 | 相关 `tests/unit/test_english_ltr_features.py`、`test_ltr_export.py`、`test_ltr_pairwise_training.py`、`test_nevir_compare_feature_versions.py` | 普通英文 61 例；错版本、规则缺失、默认回归、重载、未知矩阵来源、单配置只拟合一次等均通过 |
| 最终非 integration 回归 | 同一完整命令；[日志](../../runs/post_recall/nevir-english-features-20260907/checks/tests-after-english-adaptation.log) | **1,030 passed、3 deselected、6 warnings，10.30 秒**；包含真实生产依赖契约与导入边界 |
| Ruff | [命令清单](../../runs/post_recall/nevir-english-features-20260907/technical-entry-checks.json)及[新／相关模块日志](../../runs/post_recall/nevir-english-features-20260907/checks/lint-changed-modules.log) | 新增和其余相关模块通过；整个 LTR 目录仍有 11 项既存问题，非全绿 |
| 既存 lint 区分 | [逐文件原行为比较](../../runs/post_recall/nevir-english-features-20260907/lint-baseline-comparison.json)、[扩大检查日志](../../runs/post_recall/nevir-english-features-20260907/checks/lint-after-english-adaptation.log) | experiment 3→3、online 6→5、cache 1→1、short_query_gate 2→2；新增问题 0，未顺手清理无关代码 |
| 导入／CLI | 主 CLI、训练、旧 A/B 评测、旧诊断、新比较 `--help`；同上命令清单 | 全部退出 0，未借 help 执行实验 |
| 重训后产物复核 | [独立代码路径的保存产物算术核对](../../runs/post_recall/nevir-english-features-20260907/saved-artifact-verification.json) | 从保存分数和开发监督重算指标／来源／配对，NPZ 列响应一致，旧 B 字节一致；无新拟合 |
| 历史输入保护 | 同上核对 16 个输入／原模型文件的大小与修改时间 | 与任务记录一致，旧包与快照未写入 |
| 文档、索引、diff | [最终工程检查](../../runs/post_recall/nevir-english-features-20260907/final-checks.json) | 159 个本地链接、3 个新增锚点、报告索引及 `git diff --check` 通过；`lint-imports` 无配置 contracts，有效护栏由回归测试验证 |

在真正重训前，追加编排测试发现单配置路径仍调用六配置选择校验，已修复并保留[修复前失败日志](../../runs/post_recall/nevir-english-features-20260907/checks/tests-fixed-config-before-fix.log)；最终回归通过后才开始两次研究拟合。该测试使用普通合成夹具，没有新增 NevIR 拟合。技术测试通过与效果改善是两个不同验收问题。

## 7. 产物、工作区改动及决策

本轮唯一正式报告即本文；配置、模型和日志不会随 Git clone 自动出现。

- [实验配置](../../runs/post_recall/nevir-english-features-20260907/comparison-config.json)、[主结果与完整参数](../../runs/post_recall/nevir-english-features-20260907/comparison/comparison.json)、[实际命令／PID／耗时](../../runs/post_recall/nevir-english-features-20260907/comparison-execution.json)、[执行日志](../../runs/post_recall/nevir-english-features-20260907/comparison-execution.log)。
- [legacy 模型包](../../runs/post_recall/nevir-english-features-20260907/comparison/legacy/model-b/manifest.json)、[英文模型包（现英文基线）](../../models/english-baseline/manifest.json)；两组的 `selection.json`、`dev-predictions.jsonl` 和开发 NPZ 仍分别在原 `comparison/legacy/`、`comparison/english/` 目录。模型命名与位置的后续调整见[模型入口](../../models/README.md)，实验结果未改写。
- [76 查询比较记录](../../runs/post_recall/nevir-english-features-20260907/comparison/development-comparison.jsonl)；每条记录人工状态 pending，缺目标两条保留。
- [技术验收](../../runs/post_recall/nevir-english-features-20260907/technical-acceptance.json)、[运行产物复核](../../runs/post_recall/nevir-english-features-20260907/saved-artifact-verification.json)、[最终检查](../../runs/post_recall/nevir-english-features-20260907/final-checks.json)。

开始时已有 README、CURRENT_STATUS、DOCUMENT_CATALOG、架构、研究计划、讨论记录、报告索引及 `online.py` 的跟踪改动；已有两个 NevIR 报告、准备／采集、部分标签训练／评测／诊断与对应测试等未跟踪文件。本任务在这些已有实现上增量修改，未覆盖／撤销原有工作；讨论记录与原报告保留。当前 `git diff` 因包含前轮改动而不是本任务净 diff，且不会显示未跟踪源码内容；初始差异保留在 §1。本轮主要源码增量是提取特征核心、英文规则、模型契约、单配置训练和比较编排，对应测试及入口文档同步；当前跟踪 diff 为 9 文件、+443/−344 行（含此前改动）；本任务另新增 6 个未跟踪文件，其中只有 1 份正式报告。完整列表见[差异记录](../../runs/post_recall/nevir-english-features-20260907/working-tree-summary.json)。

**下一步只建议完成现有 76 查询盲审，再将复核结果与已有纠正／损害记录关联。** 本轮停止基础英文规则效果迭代，隔离英文版作为已测试的可选研究版本保留，不替换 legacy／B，也不自动启动这个人工步骤、文本模型、门控、新确认或 Test。无关键输入阻断；语义归因待人工复核，lint 有上表明确既存问题。

开发集参与过旧 B 选择，也参与本轮树数选择；本轮是开发比较，不是独立验证。不声称自然业务收益、最终回答质量提升、否定理解已改善或 38 维已达上限。

## Material Passport

- 来源：当前本地代码、旧 A/B 模型包、已保存 Train／开发候选与官方成对监督；未读取确认／Test 逐题。
- 整理：本任务按 academic-research-suite 的代码执行与证据区分要求内联完成实现、测试、两次拟合和保存产物复核；没有把代理判断当成人工标签。
- 状态：结构／英文实现／版本隔离／受控比较完成；开发效果为负；人工语义归因 pending。未追加规则、参数或模型。
