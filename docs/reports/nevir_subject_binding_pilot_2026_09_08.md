# NevIR：自动事实条件聚合与独立盲审交付（2026-09-08）

**最新工程修复已完成（§3.5）：版本传错、查询／正文类型不对称、主体未解析就删除事件均已修正，并增加真实 parser 贯通测试。** 新 v3 在原开发快照中有 8 条查询出现候选间数值区分，合法 Train 指定对中有 6 条，基础匹配准入通过；三种聚合仍相同，绑定比较准入未通过。固定 E0／EM／E1 三次拟合已完成，新增列仍未进入树分裂，完整预测分别与原实验相同，不能把历史点增益算作本次修复的收益。旧规则、缓存、模型与结果保留，§3.4 的 v2 零拟合是前一阶段事实。

当前判断是：表示层工程缺口已得到具体修复，但新信号尚未被模型利用，主体绑定的核心假设仍未有效受测。上游信息丢失有机械证据支持，不能由此认定它解释全部错排，也不保证进一步修复会涨分。

本报告为台账 **N08** 的唯一正式实证记录。设计维护于[研究计划 §2.7](../plans/post-recall-research-plan.md#27-同一自动事实上的条件聚合对照2026-09-08)，进度维护于[CURRENT_STATUS](../CURRENT_STATUS.md)。两名审阅者均 76/76 完整；负责人第五批明确第 60 题后，**76 条成对处置全部接收，待明确 0 条**，其中 4 条人工未决保留。最新 v5 的严格方向且共同覆盖分母为 **52 题**：E0 为 31/52，EM、E1/E2/E3 各 32/52，相对 E0 仍纠正 3、改坏 2（§2.8）。v4 的 51 题分析保留在 §2.7。官方 74 题统计保持；研究判断更新为上游信息丢失的待验证假设（§3.3），抽取语义准确率仍未人工核验，本轮没有独立确认或 Test 评分。

## 1. 输入、历史重放与实际文件边界

执行依据为用户提供的完整说明，原样副本见[execution-instructions.md](../../runs/post_recall/subject-binding-pilot-20260908/execution-instructions.md)。工作分支 `feat/nevir-ltr-validation`，HEAD `55cdf31f2cc8d388de57689f5ce26b1486220ee2`。初始状态、原有未提交差异分别在 [initial-state.json](../../runs/post_recall/subject-binding-pilot-20260908/initial-state.json) 和 [before-work.patch](../../runs/post_recall/subject-binding-pilot-20260908/checks/before-work.patch)。没有切换分支、提交、推送、重新召回、修改 BM25 或恢复 Qwen/BGE；旧模型、候选、实验目录均未覆盖。

- Train：原计划 1,896 查询，269,941 行完整候选。25 条指定两段未共同召回、2 条结构冲突排除，1,869 查询／3,738 行进入原有相对偏好损失，472 个合法监督来源组。背景只参与池特征，不进入负例。
- 开发：原 38 对／76 查询／10,465 候选行，74 查询／37 对共同覆盖，19 来源组。缺失目标不补入。训练与开发沿用原来源隔离、结构冲突和来源平衡规则，实际 summary 除计时外与 N06 对应字段核对通过。
- [配置](../../runs/post_recall/subject-binding-pilot-20260908/config.json)只显式传入 Train／development 文件；未调用会遍历所有划分的入口，未读取确认或 Test 的逐题查询、标签、分数或表现。
- [历史重放验收](../../runs/post_recall/subject-binding-pilot-20260908/stage-a/development-input/preparation.json)：重算的英文 38 列与 N06 NPZ 完全相同；历史 B 与英文的完整池分数、排序、偏好记录与原保存文件完全一致，分别为 47/74、44/74。E0 重训后模型文本与冻结英文模型逐字节相同。

| 职责 | 本轮位置与变更 |
| --- | --- |
| 原 38 列与在线两模型 | 原 `features.py`、`online.py`、`models/chinese-baseline/`、`models/english-baseline/` 保留 |
| 自动事实、三个聚合与文本缓存契约 | [subject_binding.py](../../src/linkrag_eval/retrieval/learning_to_rank/subject_binding.py)，在现有特征模块体系内新增；无来源 ID、标签、配对或召回调用 |
| 离线 41 列模型契约 | [subject_binding_model.py](../../src/linkrag_eval/retrieval/learning_to_rank/subject_binding_model.py)，明确英文基底、臂、列顺序、缺失和规则版本，旧在线加载器不接受 |
| 共享训练机制 | [pairwise_training.py](../../src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py)仅给原固定单次 fitter 增加有序列名参数及宽度检查；原默认仍为 38 列 |
| 一次性编排 | `scripts/subject_binding_{parse,controls,development,training}.py`；复用原快照校验、成对损失、来源权重、早停与预测入口 |
| 分发和未来收件 | [review_handoff.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_handoff.py)与 `scripts/nevir_review_{handoff,receive}.py`；复用 N05 页面，不重建平台 |
| 实验数据和环境 | ../../runs/post_recall/subject-binding-pilot-20260908/；大型矩阵、原文、缓存、模型、日志与隔离 parser 环境都在 runs 内 |
| 测试 | `tests/unit/test_subject_binding.py`、`test_subject_binding_model.py`、`test_review_handoff.py`；原相关测试保留 |

没有为了整理而搬运历史文件。既有未提交的 AGENTS、README、CURRENT_STATUS、DOCUMENT_CATALOG、REPORT_INDEX、索引生成器和实验台账改动保留；本轮在相应入口追加 N08。根目录原附件保留为用户提供的未跟踪文件。

## 2. 两份标注包与收件状态

**最终使用的是 §2.3 记录的 `handoff-structured-v2` 材料；两份最终 ZIP 当前缺失，公共文件与映射仍在，已有提交可正常使用。** §2–2.6 按各次交付保留历史事实，当前人工结果与已完成分析以 §2.7 为准。下方初版、§2.1 和 §2.2 不再作为分发入口。

- [reviewer_1_package.zip](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff/reviewer_1_package.zip)
- [reviewer_2_package.zip](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff/reviewer_2_package.zip)

每份只有该人的 `review.html`、`cases.jsonl`、`blank-answers.jsonl` 和同一份中性 `README.md`。原三份公共文件逐字节复制 N05；两人各自的 76 查询、152 个正文展示、匿名编号、顺序、X/Y 位置与原私有映射逐项一致。没有重新抽样、打乱、生成编号或把缺失目标加入候选。ZIP 成员白名单、CRC 和解包字节通过，公共材料没有私有映射、官方方向、模型结果或另一人的意见。详见[分发 manifest](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff/handoff-manifest.json)，该 manifest 属于研究侧，**不随 ZIP 分发**。

使用方式：分别解压自己的一份，先读 README，用桌面浏览器打开 `review.html`；姓名可用稳定代号，类型选人类，每人完成全部 76 条。选择 X/Y 原文证据、填写适用性与理由，保存后点击“下载结果”。交回各自完整 `reviewer_1-answers.json`／`reviewer_2-answers.json` 原文件，不能只交截图。最初页面以原打开位置的浏览器本地存储恢复草稿，当时没有 JSON 导入功能；新版已补齐（见 §2.1），仍应频繁下载备份。file 访问有问题时，README 给出只暴露自己公共目录的本机 localhost 方法。

**验收限制：**自动浏览器打开 file URL 被 Browser URL security policy 拒绝，未尝试其他入口绕过。因此没有实际浏览器中的视觉、保存恢复或下载验收。已有页面的 Node 模拟 DOM 测试覆盖保存、恢复、导出和 Unicode 摘录校验，公共文件与该受测 renderer 完全一致；这不等于实际浏览器验收。

初次分发时，收件入口已用纯合成测试验证，尚未用于真实提交；当时命令如下：

```bash
.venv/bin/python scripts/nevir_review_receive.py \
  --manifest runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/handoff-manifest.json \
  receive --reviewer reviewer_1 --submission /绝对路径/reviewer_1-answers.json \
  --out runs/post_recall/subject-binding-pilot-20260908/human/reviewer_1-v1

.venv/bin/python scripts/nevir_review_receive.py \
  --manifest runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/handoff-manifest.json \
  disagreements \
  --reviewer-1-intake runs/post_recall/subject-binding-pilot-20260908/human/reviewer_1-v1 \
  --reviewer-2-intake runs/post_recall/subject-binding-pilot-20260908/human/reviewer_2-v1 \
  --out runs/post_recall/subject-binding-pilot-20260908/human/adjudication-v1
```

每次收件使用新目录，先保存只读原始字节、时间、哈希和身份，再单独记录规范化内容及格式、必填、枚举、重复／遗漏、ID、证据摘录与 Unicode 位置问题。原始旧导出不带正文版本键；新版 durable 导出包含内容绑定的 storage_key，主会话验收已补后端核对，见 §2.2。旧导出仍仅按其原 ID 集和已核对分发包关联。多版本不能自动选“最终版”。

两人通过原私有映射对齐，不按第几题或 X/Y 直接对齐；分歧材料保留两份判断和原文，仍不显示官方／模型结果。初次方案要求选项相同也由人类核对理由是否冲突，并记录裁定身份、时间、版本；程序不投票、不解释分歧、不产生金标。负责人锁定后才关联本轮已保存模型结果，不重训、不改官方统计。初次分发时未创建假收件或假裁定；后续真实收件见 §2.4–2.5，负责人最终接受规则、实际来源及已完成分析见 §2.7。

### 2.1 分发页面持久化修订（2026-09-08，侧栏请求）

负责人要求补强独立标注员的保存可靠性。**该次持久化修订曾分发[审阅者 1 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/reviewer_1_package.zip)和[审阅者 2 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/reviewer_2_package.zip)。** 上述旧包记录保留供追溯；旧 ZIP、N05 页面、正文、编号、顺序与私有映射没有覆盖。新版 `cases.jsonl`、空白模板以及页面内嵌数据／存储键与原版一致。

新增输入即时自动保存、明确保存失败提示、未下载备份的离开提醒、带时间的 JSON 备份、JSON 导入续填。未完成或证据位置暂时不一致的原始字段也作为草稿保存；本地存储报错时仍可下载备份或结果。导入检查包、正文版本、匿名编号、证据和字段；替换已有草稿需确认并先发起现有备份下载，错误／取消不替换。其他窗口修改同一草稿时停止覆盖保存并提示备份。

保存只是当前浏览器的本地副本；每次结束仍须下载 JSON 并确认文件实际存在。没有服务器或后台自动上传，无法承诺设备损坏、清理数据或未完成下载后也绝不丢失。新版 README 已明确这些边界及恢复步骤。普通答案导出维持 schema_version=1，附带可恢复草稿；已有收件检查可接受，不改人类判断或模型结果。

实现：[review_persistence.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_persistence.py)；通过 16 项新增持久化用例及既有页面／收件回归，共 **64 passed**。两个实际新版包分别进行了 76 条临时草稿的 JS 导出／导入逐值检查，内容和私有标识隔离校验通过。测试仅在 Node 模拟环境执行，没有写真实人工提交；**真实浏览器验收仍未执行**。[验收记录](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/acceptance.json)与[测试日志](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/tests.log)保留。该次版本的收件 manifest 为 `handoff-durable-v1/handoff-manifest.json`；当前新版入口见 §2.3，仍连接原 N05 私有映射。

**学生入门页补充。** 根据负责人的侧栏请求，两份新版 ZIP 均加入相同的独立[标注入门.html](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/reviewer_1/标注入门.html)：三个自编讲解示例、三道先填后看参考标注的练习。面向非专业学生说明四种适用性、查询歧义、相对偏好和证据理由；仅展示参考，不比较选项、不评分。六道材料均非 NevIR 正式样本，也不进入人工金标或模型实验。练习使用独立本地存储，不能改动正式 76 条；两份教程与说明一致。原 `review.html`、cases 和空白模板字节不变，之前分发的 ZIP 已保存到 `handoff-durable-v1/archive-before-tutorial/`。离线脚本检查了三题填写门槛、参考初始隐藏、展示后保留作答、刷新恢复、清空隔离以及存储失败时仍可练习；[检查记录](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-durable-v1/tutorial-checks.json)保留，未进行真实浏览器视觉验收。

### 2.2 主会话独立验收：填写后能否用于正式收件

**通过：该次验收的两份 durable-v1 包中完整、合规填写后导出的最终 JSON，可以按对应旧版 manifest 收件。** 当前结构化版的验收见 §2.3。 这里确认数据链路与程序契约，不保证任意浏览器／设备上绝不丢失，也不把填写完整当作语义正确。

本次直接读取 `handoff-durable-v1` 两个实际 ZIP 内的页面脚本，以包含真实 HTML 控件、真实 select 选项及事件的 DOM 模拟逐题填写，而非只构造后端 JSON。每份 76 条都走过逐输入自动保存、仅凭本地存储刷新恢复、备份／最终导出、空白存储环境导入再导出；恢复结果逐值一致。之后实际调用 `receive_submission`，两份均 76/76 完整、零格式／身份／Unicode 证据错误，原文件只读副本逐字节相同。

这批程序生成文件的身份与理由明确标记 QA ONLY，原始、规范化及待裁定文件只放独立系统临时目录，没有作为人类结果、训练或语义证据；该次验收时为 **0/2 人类提交**。用原私有映射核对全部 76 条，正确处理审阅者 2 的 40 条 X/Y 互换，准确得到预设 7 条 QA 分歧；没有自动锁定判断或关联模型。

验收查实并修复：

1. 新版导出的 `storage_key` 已绑定原正文与匿名顺序，后端此前忽略它；新增错版本拒绝检查，原始无此字段的导出明确记录为 legacy。失败复现见 [version-mismatch-before.log](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/version-mismatch-before.log)。关联阶段还须核对收件所用分发包版本，防止错误 manifest 混用。
2. 对齐后两人的选项已转换为统一 X/Y，但原始理由中的字母不能自动改写。现保留每人的原 case ID、原选项、原段落标记及原 X/Y → 统一 X/Y 的说明，避免把第二人的原 X 理解成第一人的 X；理由本身不改写。
3. 即使查询歧义字段和相对偏好未选不确定，只要单段判断为“无法裁定”，也加入人类不确定清单；仍不替人裁定。

教程的 21 个真实必填控件（3 题）逐项检查通过：未填完或选项不合法时参考区保持隐藏；全部完成后只展示参考，不评分；刷新恢复填写和展示状态；取消重置不改记录，确认重置不动正式存储键；本地存储失败仍可练习。另用含 emoji 的独立单元样例验证选择证据的 Unicode 字符偏移，未将 emoji 填入正式正文。

**限制仍明确：没有真实浏览器渲染、磁盘下载或跨 Chrome／Firefox 的现场验收。** 前次 file URL 导航被 Browser URL security policy 拒绝，本次未绕过。空白 DOM 存储环境导入不是实际换浏览器，模拟 Range 也不是原生鼠标选中文字。审阅者仍应按 README 确认 JSON 已实际下载到磁盘。

相关回归 **67 passed**；完整非 integration **1100 passed、3 deselected、6 warnings，12.02 s**；五个相关源码／测试文件 Ruff 通过。详见[本次验收](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/acceptance.json)、[端到端记录](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/packet-end-to-end.json)、[相关测试](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/related-tests.log)、[完整回归](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/full-regression.log)。

没有修改 ZIP 内材料，两个实际分发包的 SHA 与本次验收前相同，仍各含 5 个公共文件；正文、编号、顺序、教程及旧包均保留。本次仅修正式收件／对齐程序、补测试及记录，没有重训、召回或读取确认／Test 逐题。

### 2.3 结构化原因选择：当前分发与收件契约

负责人经侧栏明确要求降低重复自由文字负担。本次同步修改正式页面、教程、草稿／备份／导出、接收／对齐程序与文档；只调整审阅工具，没有新模型实验。**该轮分发为 `handoff-structured-v2/reviewer_1_package.zip` 与 `reviewer_2_package.zip`，每人独立完成全部 76 条。** 现有表单：[审阅者 1](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/reviewer_1/review.html)、[审阅者 2](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/reviewer_2/review.html)；当前 ZIP 缺失情况见 §2.4。

| 保留或新增 | 具体规则 |
| --- | --- |
| 保留四种适用性、歧义、相对偏好、复核状态 | 选项和含义沿用；程序不会从原因选项推导偏好或相关性 |
| 每段多选依据 | 人物对象、行为关系、肯定否定、时间数量比较、缺少信息、歧义矛盾、其他／说不清。类型描述审阅者所用证据，不是模型机制标签；通常至少一类，查询歧义导致无法裁定时的例外见 §2.4 |
| 条件摘录 | 支持／明确不满足必须给逐字原文与 Unicode 位置；证据不足／无法裁定可以无摘录 |
| 条件补充 | 证据不足要选具体缺失内容类型或写短注，只选缺少信息不完整；无法裁定或选择其他必须短注。普通清楚情况可留空 |
| 比较依据 | 8 个固定选项覆盖单段优势、双方支持／不足／不满足、质量差异、歧义和其他；特殊比较或不确定时写短注。相对偏好独立保存，绝不按原因码改写 |
| 教学 | 3 自编讲解＋3 独立练习，全部条件字段齐全后才显示参考，不计分。与正式页共用原因契约和条件检查；练习独立保存，不写正式结果 |

**字段入门说明补充。** 两份当前 ZIP 的教程已在示例前增加字段说明表，逐项解释身份、查询歧义、适用性、原因类别、摘录与自动位置、补充说明、相对偏好、比较依据和复核状态，明确四类适用性及“无严格优劣／无法裁定”的区别，并说明保存与交回。仅新增教学文字与表格样式；正式页、正文、空白模板、README、教程脚本及内嵌练习数据均保持字节一致，现有草稿和字段规则不变。更新前 ZIP 与 manifest 保存在当前分发目录的 `archive-before-field-guide/`，当前 manifest 已更新教程与 ZIP 摘要。相关回归 **93 passed**，Ruff 与 diff 检查通过，两包成员／CRC／摘要一致；见[补充验收](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/field-guide-checks.json)。未新增真实浏览器验收或人类判断。

新答案头 `schema_version=2`、`reason_schema_version=structured_reasons_v1`；单题带 `answer_schema_version=2`，新增 `pair_reason_code`，每段新增 `reason_types`。`reason`／`pair_reason` 仍原文保存，仅按上表条件必填。公共 `cases.jsonl` 与 N05 原文件逐字节一致，正文、匿名编号、X/Y 位置和顺序未变；空白模板升级结构，所有新选择为空。两份 ZIP 各含五个公共文件，不含研究侧 manifest、private 映射、官方方向、模型结果或另一人的意见。

新草稿键为原正文绑定键加 `-structured-v2`。旧格式 1 的本地草稿和 JSON 可恢复原文字与证据，新类别保持空并提示逐题补填，不从文字自动打标签。即时备份也统一使用新格式，格式错误的原始字段仍以草稿保留。旧键、旧包及旧提交不覆盖；新版 manifest 下收到旧答案会保留原文件并报告版本不符，须由审阅者导入补填后再导出，不静默当成本版完整结果。旧格式只有使用其原 manifest 才按原必填条件校验。

接收分别检查格式版本、正文键、枚举、重复原因、条件字段、匿名 ID 和 Unicode 摘录；合规普通题可以不写自由理由。规范化结果保留真实选择，统计仅是多选频数，不视为语义真值。对齐继续使用原私有映射并保留每人原 X/Y 文字语境；新增原因类型差异作为单独待人工查看项，既不自动解释，也不将选项一致当作正确。该次分发时为 **0/2** 人类提交，没有生成正式人工收件／金标；后续收件见 §2.4–2.5，当时待执行的模型关联已于 §2.7 按最终接收规则完成。

实现职责：[review_schema.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_schema.py)定义固定枚举与条件，[review_structured.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_structured.py)仅升级和打包已核对材料，[review_tutorial.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_tutorial.py)生成同契约教学页；复用已有持久化和接收模块，不新建平台。生成入口与收件命令见[脚本说明](../../scripts/README.md#n08-离线原型与人类收件)。

**实际验收：相关 93 passed；完整非 integration 1126 passed、3 deselected、6 warnings（15.82 秒）。** 规则条件的 1,536 种组合在 Python 与共享 JS 上一致；两份最终 ZIP 内实际脚本各完整填写 76 条，覆盖四种适用性、七种依据和八种比较选项，自动保存／刷新／备份／最终导出／空存储导入逐值相同，实际 Python 收件均 76/76 完整、零错误，原文件只读字节保留。原映射准确处理 40 条 X/Y 互换及 7 条预设 QA 分歧，无自动裁定或模型关联。旧实际 ZIP 导出的迁移、缺新增字段提示、旧键保留、跨包／正文／格式拒绝、本地存储失败备份，以及两份最终教程的条件解锁／恢复／清空隔离均通过。含 emoji 的单元样例验证按 Unicode 字符而非 UTF-16 单元计位置；未改正式正文。

程序生成的答案与收件只在独立系统临时 QA 目录，不进入研究标签、语义准确率或效果统计。**真实浏览器渲染、原生选文、磁盘下载及跨浏览器现场验收仍未执行**：此前 Browser URL security policy 拒绝继续有效，没有改走其他入口绕过。这里通过的是最终 HTML 的 DOM 模拟和真实 Python 数据链路；审阅者仍需确认 JSON 实际下载成功。

产物：[分发 manifest](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/handoff-manifest.json)仅供研究侧，[验收](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-structured-audit/acceptance.json)、[最终包链路记录](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-structured-audit/packet-end-to-end.json)、[相关测试](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-structured-audit/related-tests.log)、[完整回归](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/handoff-structured-audit/full-regression.log)。旧包保留，未新增训练、召回、确认／Test 读取；N08 的官方探索结论不变。

### 2.4 查询歧义的完整性例外与原提交兼容验收（2026-09-09）

**reviewer_1 第 20 题无需补写；其全部 76 条按新规则可接收。** 该题已经选择查询有歧义、两段无法裁定和比较无法裁定，并分别说明疑点；空的是两段的 `reason_types`，而非本来必填的正文摘录。原规则要求每段至少一类，错误地将这种有说明的弃权判断判为未完成。本次根据负责人的反馈修正完整性标准，不修改任何人的选择或文本，也不据此认定查询在语义上确有歧义。

| 情况 | 当前验收规则 |
| --- | --- |
| 查询歧义为 `yes` 或 `uncertain`，本段为“无法裁定”，且本段说明非空 | 本段 `reason_types=[]` 可接受；原文摘录本来就可为空。X/Y 各自判断，不自动补选类别 |
| 查询无歧义、未回答歧义、其他适用性，或本段说明仅空白 | 不适用该例外，保留相应必填检查 |
| 支持／明确不满足 | 仍必须提供匹配正文的摘录；查询有歧义也不免除 |
| 已填摘录、类别字段及其他条件字段 | 已填摘录仍核对 Unicode 位置；缺字段、`null`、未知／重复类别仍报格式错误；比较依据、条件说明等不变 |

**兼容方式。** 答案格式仍为 `schema_version=2`／`structured_reasons_v1`，正文绑定存储键、匿名编号、字段和词表不变；收件程序独立记录 `validation_policy_version=query_ambiguity_abstention_v1`。旧 JSON 不需要新增该字段或重新导出，提交自行声明的策略也不能覆盖实际校验器。程序从原答案重算完整性，旧页面写出的 `completion` 只保留为原始记录。格式 1 的原校验不变。

Python 接收、共享 JS、正式表单提示、教程练习及字段说明、生成包 README 均已同步。**本次没有修改现有分发表单／manifest、真实提交或旧收件，也没有重新打包。** 因此旧页面仍可能显示旧的缺项提示，以新收件结果为准；无需为了 reviewer_1 第 20 题重新标注。新页面生成器使用修订规则，原有已填写 JSON（包含 `drafts`）可以直接恢复。

| 该次原始提交 | 原规则完整数 | 修订规则完整数 | 当时需补写 | 技术错误／缺失题号 |
| --- | --- | --- | --- | --- |
| reviewer_1 | 75/76 | **76/76** | 0 | 0／0 |
| reviewer_2 | 47/76 | **47/76** | 29 | 0／0 |

“完整”包括有说明的无法裁定，**不等于得到可判相关性金标**。当时 reviewer_2 的待补项是其他条件说明、歧义选择或必要摘录，本例外没有改变其验收结果。该阶段按负责人的“需补写即中止”要求暂停后续分析；指定补写文件的续接见 §2.5。

原规则收件及当时生成的未裁定材料保留在 [20260909-intake-v1](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-intake-v1/)；其中混合缺项、不确定与不同选择的标记数不能当作人类分歧率。当前新规则的[兼容验收](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/compatibility.json)、[reviewer_1 收件](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/reviewer_1/receipt.json)和 [reviewer_2 收件／缺项](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/reviewer_2/receipt.json)写入独立目录，均只供研究侧使用。验证了原始文件逐字节保留、已有收件和分发 manifest 未变；接收同时核对原公共文件与私有映射。当前渲染器直接导入两份原始 JSON，含原 `drafts` 的答案、草稿及存储键在导出后逐字段一致，完整数与 Python 接收一致。验证脚本位于同目录 `check_compatibility.py`；采用 Node DOM 模拟，未新增真实浏览器现场验收。

相关测试 **111 passed**；完整非 integration **1144 passed、3 deselected、6 warnings（16.61 秒）**。共享 Python／JS 规则覆盖 6,144 个条件组合，另测单段例外、其他必填、无效摘录、旧策略头兼容、无自动补选及教程解锁；格式 1 和既有保存恢复回归通过。首次新增测试的 9 项失败来自测试只修改 `answers` 却保留旧 `drafts`，修正合成夹具后通过；真实文件验证保留了原始两者，没有用删草稿代替兼容证明。[相关测试日志](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/related-tests-final.log)、[完整回归日志](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/full-regression.log)保留。

工程检查：相关 Ruff、两个 CLI 入口、报告索引和 `git diff --check` 通过。文档链接核对发现原最终两份 ZIP 在本地缺失；上一轮 Git 正文已有这四处链接，公共文件、原映射及人工 JSON 均完整，故不阻断本次收件，也不重建 ZIP 补齐。当前导航改指向现存表单，历史分发文件名保留；具体检查见 [engineering-checks.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/20260909-ambiguity-policy-v1/engineering-checks.json)。

本轮分支 `codex/nevir-human-review-20260909` 基于 `5afd458b2e69695b99127a83d9ea6e6b183cc0ec`；远端没有 `origin/main`，已从实际默认 `origin/master` 获取最新版本后创建。此前收件过程中已写入的“缺项与已填字段分别标记”代码及两项测试保留，并纳入回归；未用它重算真实人类比较结果。当前无新增模型实验，未提交或推送，根目录既有未跟踪附件保留。

### 2.5 指定补写版本接收与人类裁定清单（2026-09-09）

**两份指定文件均为 76/76 完整，不再需要补写。** 本次只接收负责人明确指定的 `reviewer_1-2026-09-09T02-00-21-215Z-answers.json` 与 `reviewer_2-2026-09-09T04-32-26-934Z-answers.json`，不按目录时间自动选“最新”。reviewer_1 与上次文件逐字节相同；reviewer_2 相对上一版恰有 29 条答案变更，原待补项全部齐全。原始提交分别只读保存至新的 [20260909-intake-v2](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/)，之前的提交和收件均保留。

接收沿用 §2.4 的 `query_ambiguity_abstention_v1`，两人均零格式错误、零缺失 ID、零条件缺项；不填造空类别或推断人类选择。原 76 查询／38 对／19 来源组、匿名编号、顺序和正文通过核对，263 个摘录的 Unicode 位置有效。原私有映射正确处理 reviewer_2 的 40 条 X/Y 交换；两人的自由文字仍保留各自原 X/Y 语境，清单逐题标明对应关系。

| 机械比较项目 | 一致 | 不同 | 分母／说明 |
| --- | --- | --- | --- |
| 相对偏好 | 54 | 22 | 76 查询；仅 1 条为 X/Y 严格反向，其他不同涉及无严格优劣或无法裁定 |
| 查询歧义选项 | 68 | 8 | 76 查询 |
| 两段适用性均一致 | 51 | 25 | 76 查询；任一段不同即计该查询不同 |
| 段落依据类别集合 | 76 | 74 | 双方非空的 150 段；另 2 段有合法弃权空类别，不计一致或不同 |

按独立标记逻辑，**57 条需人类查看**：判断选择不同 33 条、依据类别不同 52 条、保留歧义或不确定 15 条、至少一人选择无严格优劣 24 条，类别重叠。这里的“依据类别不同”同时考虑比较依据码和可比较的段落类别；不等于认定理由冲突。57 不是“57 条直接判断分歧”，其余 19 条没有机械标记也不能自动成为金标。原始理由是否矛盾仍由人类核对。

产物入口：

- [收件摘要](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/intake-summary.json)：两份文件的完整性与实际策略。
- [人类裁定清单](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/adjudication/review-checklist.md)：按 reviewer_1 原顺序保留全部 76 条，标出 57 条待查看项，列出原查询、全文、双方原判断与摘录、X/Y 对应，以及空白裁定栏。
- [结构化全量清单](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/adjudication/human-adjudication-cases.json)与[带标记的 57 条](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/adjudication/disagreements.json)：所有裁定状态均为 pending，没有填入答案。
- [机械统计](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/mechanical-summary.json)与[验收记录](../../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/acceptance.json)：分母、重叠口径、原文件保留及清单核对。

清单可在 Markdown 编辑器中打开并另存副本，由两名原审阅者讨论或第三名人类填写裁定状态、以清单 X/Y 为准的最终偏好、依据、裁定者、时间和版本；无法裁定保留 unresolved。清单不显示官方方向、模型结果或有利于哪一方法的提示，不重建标注平台。

本轮无核心源码修改，沿用上一轮已通过的完整回归；本次实际收件、映射、摘录、清单保真和独立机械统计核验通过。只运行本地文件处理，无模型或远端调用，未读取确认／Test 逐题；原 N08 官方探索结论不变。该时点进入人类裁定阶段，后续部分讨论的接收见 §2.6；锁定后才关联已保存预测。程序不会把双方一致、理由更长或类别选择当作裁定依据。

### 2.6 部分讨论接收与持续裁定汇总（2026-09-09）

**批次 `20260909-01`：原表 15 行，覆盖 23 条查询。** 负责人通过当前对话转交“初步讨论”，要求维护最终结果并记录实验过程。本次只进行转录、原题号关联及明确保留项的复制，不新增语义判断。来源记录为“负责人转交的初步讨论”；未提供讨论参与者、实际讨论时间或最终锁定声明，接收时间不冒充裁定时间，不能将本批视为新的独立人类金标。

持续维护的唯一汇总数据为 [current-results.json](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/current-results.json)，[阅读视图 current-results.md](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/current-results.md)展示每题建议、讨论理由与双方原判断。全 76 条原编号均保留；首批覆盖 4、8、10、11、12、14、15、17、19、20、21、26、39、40、42、45、49、53、62、67、70、72、74。首批完成时建议为 X 9 条、Y 5 条、平局 6 条、未决 3 条（12、15、20），尚余 53 条未讨论。已记录不等于已锁定；第二批更新后的累计状态见下方。

| 录入情况 | 执行方式与边界 |
| --- | --- |
| 明确单段标签和偏好 | 原样登记支持、不满足、不足、无法裁定及 X/Y/tie/undetermined；不将“平局”改成未决 |
| 12、15 要求保留 A | A/B 已据原记录核对为 reviewer_1/reviewer_2；复制 reviewer_1 的单段标签和未决偏好。原查询歧义 yes 仍单独保留，不伪装成本批新增字段决定 |
| 70 要求保留两人标签 | 先验证双方已对齐标签和偏好确实一致，再保留并将查询歧义建议登记为 no |
| 只指定偏好或部分标签 | 8/42、19/62、21/49、40 不补推单段标签；53 只写明确给出的 X 不足与偏好 Y，其 Y 支持保留在原判断栏。除 70 外，本批未将查询歧义字段统一改成 no |
| 解释范围 | 逐字保留 used/burnt 的本题语境限制、来访学者待遇参照、旅行性质与时长区别、不得额外要求频率／实际次数／全变体无例外，以及 72 不推断额外时序与因果关系的限制 |
| 未覆盖内容 | 第 48 题仅为讨论中的参照，不加入修改；未提供的新依据类别、摘录位置、裁定身份及时间均不补造；未讨论的 53 条不以任何人的原标签自动填满 |

原讨论全文只读保存在 [20260909-01-source.md](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-01-source.md)，录入范围与接收时间见 [applied.json](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-01-applied.json)，机械验收见 [checks.json](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-01-checks.json)。后续讨论继续更新同一汇总，原批次和原始审阅提交不覆盖；既有待裁定清单仍作为全文与原意见入口。

本轮验收包括 15 行到 23 题映射、76 个匿名 ID 和原顺序、明确字段与保留字段来源、未提供字段未被填充、第 48 题未修改，以及三次既有收件的原始／规范化文件不变；均通过。这里只处理本地文件，没有核心源码修改、新模型训练、召回、模型评分关联或确认／Test 读取。N08 的官方探索指标和停止扩展决定不变；本批处理记在同一 N08 记录中，不另称一项效果实验。

**第二批 `20260909-02`：A/B 讨论后采用 A 的 9 条完整答案。** 负责人明确指定 27／76、28／33、13／38、56、64、75；这里 A 为 reviewer_1。9 条均此前未讨论，与首批无重叠。以指定收件版的 A 为来源，完整保留查询歧义、单段标签、偏好、比较依据码、理由、依据类别及摘录位置；逐题源字段副本保存在汇总的 `adopted_reviewer_answer`，不从零重新判断正文。

| 原题号 | 采用的 A 偏好 | X / Y 单段标签 |
| --- | --- | --- |
| 27 | X | 证据不足 / 明确不满足 |
| 76 | 平局 | 明确不满足 / 证据不足 |
| 28、33 | X | 支持 / 明确不满足 |
| 13、38 | Y | 明确不满足 / 支持 |
| 56 | 平局 | 支持 / 支持 |
| 64 | 未决 | 无法裁定 / 无法裁定 |
| 75 | 平局 | 明确不满足 / 证据不足 |

第 64 题保留查询歧义 yes，其余 8 题为 no。27 与 76 的原偏好并不对称，照录而不自动统一；原理由对具体性要求和比较口径的说明完整保留。该批状态记录为“负责人报告 A/B 达成一致并采用 A，整体未锁定”，与首批初步意见区分；接收时间不冒充实际讨论时间，也未伪造新的裁定者签名。

本批[原话](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-02-source.md)、[应用记录](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-02-applied.json)与[验收](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-02-checks.json)留存。更新前的汇总保存为只读 [results-v1.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/history/results-v1.json)；当前版本为 2。机械和独立核对确认 9 条完整答案与 A 原始 JSON 一致、其余 67 条结果对象不变、原始及规范化收件未变。

**第二批完成时累计 32/76 条已登记，44 条未讨论；X 12、Y 7、平局 9、未决 4（12、15、20、64）。** 首批 23 条仍为初步意见，第二批 9 条为用户报告的讨论一致；整体锁定 0 条。只修改本地汇总和过程记录，未新增训练、模型关联或效果评分。

**第三批 `20260909-03`：58／60 与 44／55 的判定表。** 本批原话、关键证据和比较补充均保存，3 条明确结果已录入，1 条有实质映射歧义待负责人确认。未把“最终判定表”的标题当成全 76 条已经锁定。

| 原题号 | 实际查询与显示 | 录入结果 |
| --- | --- | --- |
| 58 | similar to Bridge；X 带 except Bridge，Y 不带 | X 支持、Y 证据不足，偏好 X；表中“A 更适合”按其所述 X/Y 优劣对应记录 |
| 44 | would not have been sufficient；X 本人拒脱，Y 押衬衫被拒 | X/Y 均证据不足，tie |
| 55 | would have been sufficient；X 押衬衫被拒，Y 本人拒脱 | 用户“镜像同理”的两段不足、tie 对换后不变，照录；比较补充注明原讨论使用第 44 题的否定查询和左右语境，不把它误写成第 55 题原查询 |
| 60 | unlike Bridge；X 不带 except Bridge，Y 带 except Bridge | 仅“镜像同理”不能唯一决定两个标签与偏好；三个字段保留空，状态 awaiting_user，不计入 35 条已登记结果，也不把待澄清误记成语义 undetermined |

第 60 题已向负责人明确提出：是否 X 证据不足／Y 明确不满足，偏好应选 X 还是平局；未代替用户选择。此前 27 的“不足胜不满足”与 76、75 的“不同标签但平局”均保留，因而也不能借已有比较口径猜出第 60 题偏好。

原讨论的“明示与合理推测”共性说明保持原话，作用范围记录为本批讨论依据，不追溯重标此前允许语境对应的题目，也未调用外部知识验证游戏规则或故事背景。当前排序研究仍只使用保存的候选正文，不新增任何文本、规则或模型。

本批[原话](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-03-source.md)、[应用记录](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-03-applied.json)和[核对记录](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-03-checks.json)保留；上一版只读存为 [results-v2.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/history/results-v2.json)。本批引用的 6 段摘录均由给定短句在原正文中定位，记录 Unicode 范围；只是字符串匹配，不是新增人类证据判断。独立核对确认三题可录入、第 60 题确需明确；此前 32 条结果对象未改动。

**第三批完成时共收到 36 题讨论，35 题已登记，60 待确认，40 题未收到单独讨论。** 已登记偏好为 X 13、Y 7、平局 11、语义未决 4（12、15、20、64）；当时整体未锁定，无新增训练、指标比较或模型关联。

上述三批是接收历史；第四批授权、分析版本及实际模型关联见下节。未决题继续单列，不为凑满可评价分母改判。

### 2.7 采纳一致判断、固定结果与保存分数的敏感性分析（2026-09-09）

本节保留 v4、51 查询分母的历史分析；第 60 题后续收尾及最新 v5 结果见 §2.8。

负责人第四批原话为：**“其余题目，如果AB一致那就采纳即可。之后将无人值守”。** 结合此前维护最终结果及锁定后关联保存输出的授权，本次结束结果接收，将此前明确讨论与此次一致判断固定为分析版本 v4。第 60 题未获得明确裁定，不替人选择，也不阻断其他题的计算。实际讨论时间、未提供的裁定者签名均未补造；冻结时间只表示程序记录时间。本版本是**负责人汇总决定和授权采纳的一致判断**，不冒充另一次独立人类金标。

新增采纳的 40 题在查询歧义、X/Y 单段适用性和成对偏好上全部一致，新增 X 13、Y 19、平局 8。18 题的段落理由类别不同，5、29、57 的比较理由代码也不同；双方全文解释、类别和原证据分别保留，不把“结论一致”写成“理由完全一致”。此前 35 条明确结果和未指定字段均未修改。首批第 48 题原本仅被提作参照，这次因双方一致而正式采纳。

| 固定结果的处置 | 查询数 | 说明 |
| --- | ---: | --- |
| 严格方向 X / Y | 52 | X 26、Y 26 |
| 人工平局 | 19 | 不强制制造胜者 |
| 人工未决 | 4 | 12、15、20、64，保留人类选择 |
| 尚无明确裁定 | 1 | 60：A 选 X、B 选平局，“镜像同理”未唯一确定结果 |
| 合计 | 76 | 接收 75 条成对结果，另 1 条未解决 |

冻结范围是成对偏好与已明确提供的字段；首批若只指定偏好，未指定的单段标签、歧义字段仍为空，原审阅答案完整保留。评分只消费已明确的偏好，不能从空字段推断“没有歧义”或完整语义审阅已完成。

**先固定结果和口径，后读模型分数。** 只读的 [results-v4-frozen.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/history/results-v4-frozen.json)与[analysis-policy-v1.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/analysis-policy-v1.json)在模型关联前写入。政策记录的摘要由分析程序消费，用于拒绝更改后的人工输入；没有为工作区另建哈希台账。原 v1/v2/v3、四批原话和完整提交不覆盖。[当前阅读视图](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/current-results.md)维护最终结果及分析入口，固定输入保持原样。

评价规则在读分数前明确：仅纳入人工 X/Y 严格方向且两段实际共同召回的查询；分数严格大于才正确，相等仍为模型同分，不用文档 ID 破平。原 52 条严格方向中第 69 题缺候选，最终为 **51 查询、19 来源组**；只有两方向都符合该口径的 **20 对**进入双向全对分母。第 71 题既是人工平局又缺候选，因此排除原因计数有重叠：19 平局＋4 人工未决＋1 未解决＋2 缺池，排除并集为 25，不是 26。没有补入缺候选或重抽样。

#### 人工偏好口径的实际结果

| 保存的模型 | 严格正确 / 51 | 逆序 | 同分 | 双向全对 / 20 | 来源宏平均 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A（原始基线，历史参照） | 28（54.90%） | 22 | 1 | 3 | 52.19% |
| B（legacy 重训，历史参照） | 32（62.75%） | 19 | 0 | 7 | 58.77% |
| E0（当前英文基线） | 31（60.78%） | 20 | 0 | 6 | 58.33% |
| EM | 32（62.75%） | 17 | 2 | 5 | 62.72% |
| E1 / E2 / E3（各自） | 32（62.75%） | 19 | 0 | 5 | 62.72% |

来源宏平均先分别计算 19 组中的正确率，再等权平均；各组进入分母的查询数不同，不能用全体正确数替代。完整来源分布、全部 21 个模型对的四格及逐来源四格均在 [results.json](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/analysis-v1/results.json)。

| 参照 → 方法 | 共同正确 | 纠正 | 改坏 | 共同未正确 | 净增 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A → E0 | 20 | 11 | 8 | 12 | +3 |
| B → E0 | 27 | 4 | 5 | 15 | −1 |
| B → E1 | 28 | 4 | 4 | 15 | 0 |
| E0 → EM | 29 | 3 | 2 | 17 | +1 |
| E0 → E1 / E2 / E3（各自） | 29 | 3 | 2 | 17 | +1 |
| EM → E1 | 31 | 1 | 1 | 18 | 0 |
| E1 → E3 | 32 | 0 | 0 | 19 | 0 |

“正确／纠正”在本节仅指符合固定人工偏好。51 条中 46 条方向与原官方相同，5 条相反（32、35、46、52、57）；两套标签都保留，不将这 5 条自动解释成官方错误率。共同覆盖的 18 条人工平局只作描述：A、B、E0、E1/E2/E3 没有模型同分，EM 有 1 条同分；不能据此把其他严格分数方向计成错误。

**原官方 74 查询统计逐项复算未变。** A 38、B 47、E0 44、EM 45、E1/E2/E3 各 46 条严格正确。它们与本节的 51 查询分母及标签不同，不能直接比较百分比，宣称人工修订提高了模型能力。

这次人工分析没有改变原型结论：E1/E2/E3 仍全池预测相同，相对 E0 仅净增 1 题（+1.96 个百分点），双向全对反而由 6 对变为 5 对；新增列未被树使用的既有事实不变。人工偏好使剩余错排可以按明确接收规则列出，但不提供解析器的主体、关系、作用域正确性标签，因此**抽取语义准确率仍未核验，不能归因于主体绑定或宣布稳定收益**。

#### 本次输入、执行与验收

工作分支 `codex/nevir-human-review-20260909`，HEAD `5afd458b2e69695b99127a83d9ea6e6b183cc0ec`。A 读取已保存英文诊断中的 A 分数，B 读取 N08 阶段 A 重放分数，E0/EM/E1/E2/E3 读取各自开发预测；精确路径在结果 JSON。七组各 76 查询、10,465 行候选，所有查询与候选 ID／顺序一致，私有映射中的覆盖与实际分数集合一致。逐题输出只含开发数据，见 [per-query.jsonl](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/analysis-v1/per-query.jsonl)。

```bash
.venv/bin/python runs/post_recall/subject-binding-pilot-20260908/human/adjudication/evaluate_saved.py \
  --out /新的本地输出目录
```

本地读取、校验与聚合单次 **0.0442 秒**，不含结果写盘和此前人类工时；这不是模型推理成本。没有训练、模型预测、外部服务、重新召回或确认／Test 逐题读取。一次性编排在运行目录内，未新增训练框架或第二份正式报告。

验收包括 40 题一致字段、35 条旧结果不变、原始／规范化提交保真、76 题映射、154 条新采纳意见摘录定位、冻结摘要及先后顺序、51 查询资格、所有模型指标与来源四格、官方统计不变；主流程与不读取主脚本的[独立复算](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/analysis-v1/independent-check.json)全部一致。[本批采纳检查](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-04-checks.json)和[工程验收](../../runs/post_recall/subject-binding-pilot-20260908/_superseded/human/adjudication/analysis-v1/acceptance.json)记录实际范围。实现期间两次前置断言发现脚本误用审阅者显示姓名作为角色，以及旧预测使用 `wrong` 枚举；按原数据契约修正后继续，没有改人类答案、冻结政策或模型分数。

本次执行 `.venv/bin/python -m pytest -q tests/unit/test_report_index.py`，结果 **7 passed（0.07 s）**；五个相关 Python 文件 Ruff、分析 CLI `--help`、报告索引及 `git diff --check` 通过。8 份文档／阅读视图的 359 个本地链接目标均存在；该检查不代替浏览器或锚点渲染验收。

本次不改排序／收件核心源码，原有未提交改动保留。上一轮完整非 integration 1144 passed 属于其当时执行记录；本次只运行受影响的索引测试、一次性脚本检查和上述真实产物复算，不冒称重新完成全仓回归。第 60 题保持未解决，实际浏览器验收和抽取语义准确率也未由本次补齐。未 commit/push。

### 2.8 第 60 题收尾与 v5 更新（2026-09-09）

负责人明确提供最终填写：**X 相关但证据不足、Y 明确不满足必要条件、偏好 X**。X 说明 Hearts 避墩，却没有明确 Bridge 不避墩；Y 按本轮对 except Bridge 的解释，与所问比较关系相反，因此相对选择 X。完整原话与来源保存在[第五批原文](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/batches/20260909-05-source.md)。这里只转录用户结论，不自行重新裁定，也不将 X 描述为已经充分支持答案。

实际显示已核对：第 60 题 query 为 unlike Bridge，X 不带 except Bridge，Y 带该括号。新版只改第 60 题对象，其他 75 个结果对象逐项不变；本次未指定的查询歧义字段仍为空，双方原始判断中的 no 保留，未造新的理由类别或原文摘录。此前“未获明确裁定”的状态结束，12、15、20、64 四题的人类未决保持原样。

最终分布为 **X 27、Y 26、平局 19、人工未决 4，共 76**；严格方向 53 题，第 69 题仍缺候选，实际评价 **52 查询／19 来源组／21 完整双向配对**。新增完整配对为 58/60；第 71 题仍同时属于平局和缺候选，排除并集为 24。沿用同一严格相对偏好口径，不额外要求胜者必须标签为“支持”，不因模型表现选择是否纳入第 60 题。

| 保存模型 | 严格正确 / 52 | 逆序 | 同分 | 双向全对 / 21 | 来源宏平均 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A（原始基线） | 29（55.77%） | 22 | 1 | 3 | 53.07% |
| B（历史重训） | 32（61.54%） | 20 | 0 | 7 | 57.46% |
| E0（英文基线） | 31（59.62%） | 21 | 0 | 6 | 57.46% |
| EM | 32（61.54%） | 18 | 2 | 5 | 61.84% |
| E1 / E2 / E3（各自） | 32（61.54%） | 20 | 0 | 5 | 61.84% |

| 参照 → 方法 | 共同正确 | 纠正 | 改坏 | 共同未正确 | 净增 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A → E0 | 20 | 11 | 9 | 12 | +2 |
| B → E0 | 27 | 4 | 5 | 16 | -1 |
| B → E1 | 28 | 4 | 4 | 16 | +0 |
| E0 → EM | 29 | 3 | 2 | 18 | +1 |
| E0 → E1 | 29 | 3 | 2 | 18 | +1 |
| EM → E1 | 31 | 1 | 1 | 19 | +0 |
| E1 → E3 | 32 | 0 | 0 | 20 | +0 |

E2/E3 与 E1 的完整预测依旧相同。第 60 题原保存分数中，只有 A 偏向 X，其他六组偏向 Y；所以新版 A 多 1 条符合人工偏好，其他组正确数不变。**这次改变的是人工纳入范围，没有模型权重或分数改变。** E0→聚合版本仍净增 1 条，分母更新后的点差为 +1.92 个百分点，不能宣布稳定改善或主体绑定有效。

52 条中 47 条人工方向与官方相同、5 条相反；共同覆盖的 18 条人工平局继续只做方向描述，原官方 74 条统计完全不变。全部 21 个模型对的四格与逐来源分布见[最新实际结果](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/results.json)，逐题关联见[per-query.jsonl](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/per-query.jsonl)。

[v5 固定人工输入](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/history/results-v5-frozen.json)与[评价政策 v2](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-policy-v2.json)在本次重新关联前写入；原 v4、政策 v1、analysis-v1、两份原始提交和历史阅读视图均保留。**v4 开发结果此前已经曝光**，本次是明确人工补充之后的描述性更新，不能称为重新获得未曝光数据或独立预注册。政策只变更人工版本及未解决项状态，分数比较、来源分组和评价指标沿用原规则。

```bash
.venv/bin/python runs/post_recall/subject-binding-pilot-20260908/human/adjudication/evaluate_saved.py \
  --policy runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-policy-v2.json \
  --out /新的本地输出目录
```

本地读取、核对与聚合耗时 **0.0508 秒**，范围与 v4 相同，不含写盘或人类工时；无训练、模型预测、远端调用、召回或确认／Test 读取。旧 CLI 默认仍重放 v4；新增显式 `--policy` 选择 v5，不覆盖旧结果。

验收覆盖：其他 75 个结果对象和原始提交不变，最新分母及全部指标独立复算，默认 v4 重放逐题字节一致、除时间外全部结果字段一致，错误摘要／版本政策被拒绝，相关脚本 Ruff 和文档入口检查通过。见[本次验收](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/acceptance.json)、[独立复算](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/independent-check.json)及[默认行为与政策校验](../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/regression-checks.json)。本轮不改排序或收件核心，未重新执行全仓测试、未 commit/push。

**该轮收尾时没有待明确题目，四条人工未决保留。** 当时建议停止当前原型扩展；后续上游诊断使当前行动收窄为停止原样重复训练、先定位信息丢失，见 §3.3。

## 3. 固定原型、构造探针与覆盖

使用唯一小型依赖解析器 `spaCy 3.8.16 / en_core_web_sm 3.8.0`，排除 NER，仅用分词／词元、依存和分句；安装在隔离环境，不修改原训练 `.venv`。组件和模型版本用途参照 [spaCy 官方模型说明](https://spacy.io/models/en)与[语言特征文档](https://spacy.io/usage/linguistic-features)，这不是对其本任务语义准确率的保证。实际依赖清单与加载配置见 [parser-requirements.txt](../../runs/post_recall/subject-binding-pilot-20260908/environment/parser-requirements.txt) 和 [parser-config.cfg](../../runs/post_recall/subject-binding-pilot-20260908/stage-a/development-parse/parser-config.cfg)。

规则及完整源码摘要在开发新分数前写入 [extraction-spec.json](../../runs/post_recall/subject-binding-pilot-20260908/extraction-spec.json)。只允许精确重复完整姓名、明确语法共享主语和明确关系从句先行词；代词、被动、复杂补语、条件／析取或引用范围等按冻结规则标记不支持。原子匹配保留谓词、宾语／补语角色及词元、极性、情态；不做同义词映射。所有事实保存原文 Unicode 起止位置，正文不改写、不截断；三个聚合用完全相同的事实和匹配函数。

K<2、共享主体不清或查询任一必要结构不支持，三项都缺失；正文无可用事实也缺失，部分事实可用时保留并标 `extraction_incomplete`。无词面支持的 0 仅是抽取匹配结果，不是负相关标签。缺失在 LTR 中用 NaN，EM 最后一列始终为 0。缓存键包含原文及固定 parser／规则契约，不使用标签、来源组或配对 ID。

### 3.1 十二个固定构造场景

每类 4 场景、每场景两段／两条互补查询／保义改写。文本和预期在解析前固定，未根据失败改名或加规则。理想结构的聚合定义通过单元测试；自动解析得到：

| 构造类别 | 原始查询数 | 与作者预期同方向 | 同分 | 反向 |
| --- | ---: | ---: | ---: | ---: |
| 重复全名跨句 | 8 | 4 | 4 | 0 |
| 同句多个主体 | 8 | 3 | 5 | 0 |
| 语法共享主语 | 8 | 8 | 0 | 0 |

24 条原始查询及其改写都通过原型的查询结构条件；12 场景改写的新分数均不变。9 条同分保留为失败诊断，部分解析把词性／依存边界判成其他结构，未补专门名字或词表例外。**这里的“预期”是 AI 撰写构造材料的意图，不是人工金标或真实排序收益。**

实际计算原字符 2/3-gram 覆盖及现有英文 `condition_coverage`，24 个原始 query–段落对照有 16 个在这些列上相同。不能推断完整 38 维相同，因为构造文本没有实际三路分数，未伪造这些输入。[control-scenes.json](../../runs/post_recall/subject-binding-pilot-20260908/stage-a/control-scenes.json)、[control-final.json](../../runs/post_recall/subject-binding-pilot-20260908/stage-a/control-final.json)保留全部场景、分数、失败原因和字符计算。

第一次构造解析后、开发评分前，语法审查修正了共享情态词只能继承到裸不定式且保留情态证据位置；测试正反例通过。未改构造文本，原 `control-results.json` 保留，最终用同一原始 token 缓存按冻结规则复算。此后没有按 NevIR 表现改提取规则。

### 3.2 原开发材料覆盖

| 项目 | 实际结果 |
| --- | ---: |
| 查询结构可支持 | 10/76 |
| 候选行可计算三项分数 | 635/10,465 |
| 查询不支持的候选行 | 9,218 |
| 查询支持但正文无可用事实 | 612 |
| 可用候选分数 | 635 行均为 0 |
| 指定两段均可计算的查询 | 4/74（2 对、2 来源组） |
| 指定两段新分差 | 4 条均为 0；其余缺失 |
| 正文抽取不完整 | 1,642/1,642 个不同正文；标记在全池恒为 1 |

K 分布为 0 条件 47 查询、1 条件 15 查询、2 条件 14 查询；其中 4 条虽有两个条件仍因其他结构不支持而拒绝，不缩小分母凑满分。状态和缺失具有变化，满足附件继续阶段 B 的机械条件；但三种聚合没有区分信号。全部原文、自动结构、事实、逐行分数、查询覆盖与失败原因见[阶段 A 目录](../../runs/post_recall/subject-binding-pilot-20260908/stage-a/development/)，数值支持不等于人工认定结构正确。

Train 同样只有 242/1,896 计划查询支持；269,941 行中 18,039 可计算（18,026 个 0、13 个 0.5），三种聚合全等。进入损失的 3,738 行中有 304 可计算（300 个 0、4 个 0.5）；两段均可用的 138 训练查询也全同分，其余 1,731 查询至少一段缺失。[损失行检查](../../runs/post_recall/subject-binding-pilot-20260908/checks/loss-signals.json)给出确切分母。因此本次 E1、E2、E3 在监督行和全候选上输入等同，未形成可比较的绑定差异。


### 3.3 上游信息丢失：侧对话交接核验与当前工作假设（2026-09-09）

负责人通过[侧对话](codex://threads/01a08520-b98c-73f3-bbb0-452636867000)要求收窄研究判断。此前的负结果没有证明聚合思想无效；新发现把诊断推进到具体上游实现环节。本节在原有保存输入上核查，保留 v4、v5 和所有原训练事实；[交接依据](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/handoff.md)与[实际核查结果](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/summary.json)单独存于运行目录，不另起正式报告。

| 人工口径及模型表现 | 查询结构被拒 | 两段均无可用事实 | 两段聚合均为 0 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| v4 全部严格且共同覆盖 | 45 | 3 | 3 | 51 |
| v4 英文基线错排 | 17 | 2 | 1 | 20 |
| v5 全部严格且共同覆盖 | 46 | 3 | 3 | 52 |
| v5 英文基线错排 | 18 | 2 | 1 | 21 |

交接采用 v4 的 20 条错例；主任务收尾第 60 题后，当前范围应为 **v5 的 21 条**。新增的 60 在查询处理阶段被拒。未被查询拒绝的错例仍只有 11、25、48；3、7、27 同样通过查询条件，却被英文基线判对。这一点说明上游退化并非错排独有，不能把这些统计当作 E0 错排的充分原因。

在两个版本各自的全部指定候选对中，新增的 `query_structure_supported`、`extraction_incomplete` 以及聚合值均逐值相同，包含缺失状态；同一候选的 loose/sentence/entity 也完全一致。此结论针对指定两段，不扩大为所有背景候选同值。读取实际模型文本确认 EM 22 棵树、E1/E2/E3 各 33 棵树，索引 38/39/40 的分裂次数均为 0。新增列没有被实际树利用，不能将此前几条净变化解释为语义聚合能力。

| 核查位置 | 已确认的程序行为与保存产物 | 结论边界 |
| --- | --- | --- |
| [修复前 subject_binding.py:128](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/subject_binding_before.py#L128) | 一个句子出现双引号，句内被遍历谓词全部先按 `quoted_statement_scope` 排除 | 这是整句拒绝规则，不区分片名引号与引述作用域；放宽后的正确性尚未检验 |
| 同文件 130–138、198–204 | 多类从句、补语、被动被拒；不足两条件或任意 issues 使整个查询不支持 | “程序不支持”不等于“人类无法判断”；不是要求立刻放开全部结构 |
| 同文件 210–215 | atomic_match 要求谓词、极性、情态相同，参数词元列表按角色精确包含 | 是存活事实之后的限制，不能替先发生的查询／提取拒绝背锅；本轮未实现语义改写匹配 |
| 修复前 subject_binding_development.py:147 | 准入只要求至少一条查询支持、全表某列不恒定 | 跨查询的状态变化便可能通过；没有验证同一查询候选有区分，也没有验证三种聚合存在区分。这解释准入检查不足，不改变当时确已执行的训练事实 |

**两个可直接追到正文的例子。** 第 7 题问 favorable reviews，原人审摘录覆盖的影评句含电影名引号。保存的两个段落中，`received` 在 Unicode 偏移 946／993 处均被记为 `quoted_statement_scope`；两段只留下逐字段相同的影评组织颁奖事实（predicate=name），聚合均为 0。第 7 题本身被 E0 判对，仍提供表示丢失的对照证据。第 11 题问用药接受频率，正文比较句里的 asserted/were/resist/take 同样受整句引号规则排除，两段最终都无可用事实；第 48 题也无事实。

这些事实与原文本、原人审摘录、缓存 token、被拒谓词的偏移／句子均已关联，详见 [examples.json](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/examples.json)。它们证实部分必要比较信息没有进入存活事实集；**不证明移除引号拒绝就能保留正确作用域、通过其余从句检查或形成非零匹配**。第 25 题虽有存活事实，但原子匹配矩阵全零；相关语义信息是否更早在正文提取时丢失，尚待逐项核对，不能仅因最终为零就认定匹配器是首因。

**当前已完成机械定位，尚未完成全部“首个语义丢失处”审核。** [21 条定位表](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/first-observed-output.md)列出每题最早可见的拒绝／空事实／零匹配状态；[详细 JSON](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/first-observed-output.json)保留最终偏好来源、原人审证据及其中重叠的被拒谓词。原独立审阅摘录不自动等同负责人后续最终判断采用的证据，程序也不从重叠推出语义裁定。

工作假设维护在[研究计划 §2.8](../plans/post-recall-research-plan.md#28-当前工作假设上游信息丢失阻断聚合)。**该假设解释的是新增聚合为何没有发挥作用，不能直接解释 E0 为何错排**：E0 只用原英文 38 列，根本不依赖本次抽取器。在该诊断阶段，修复前后对照尚未执行；后续实际工程修复见 §3.4，不能追溯把新结果算入该次诊断。当前进展是从“收益抵消”推进到可核对的表示生成问题，不是已经找到有效新方法。

本次读取与校验、原人审摘录定位、存活事实上的确定性匹配和模型文本检查共 **0.0593 秒**（不含产物写盘、人工或模型耗时）。没有解析器推理、模型推理、训练、外部服务、召回、确认或 Test 读取；只新增诊断产物并维护既有文档。验收见[checks.json](../../runs/post_recall/subject-binding-pilot-20260908/upstream-diagnostic-20260909/checks.json)，未重跑全仓回归。原标注、原模型、原结果和已有未提交源码改动均保留。

### 3.4 名词性引号与训练准入工程修复（2026-09-09）

负责人明确要求实际完成工程修复；确定性的代码缺陷无需等待全部语义归因完成。本阶段已修改、测试并完成同输入重放。**引号处理和训练准入修复通过技术验收；修复后仍没有足以进入聚合对照训练的数值区分，因此实际零拟合，没有新权重或新的准确率收益。** 以下“新增事实”指词面提取记录，不是人类确认的新事实。

工作分支仍为 `codex/nevir-human-review-20260909`，HEAD `5afd458b2e69695b99127a83d9ea6e6b183cc0ec`。原人工收件源码、报告和其他未提交修改保留；没有切换分支、提交或推送。没有移动既有源码、模型、快照或实验目录。计算逻辑仍在现有 `subject_binding.py`，版本绑定在 `subject_binding_model.py`，开发与训练入口继续复用原脚本；一次性对照编排和大型输出放在 [repair-20260909](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/)。

| 查实的问题 | 最小规则检查 | 实际修复及边界 |
| --- | --- | --- |
| 句中出现片名双引号便拒绝所有谓词 | `Mira likes "Blue Moon".` 及弯引号版本 | 配对且不含从句的名词性引号不再触发整句拒绝；保留主体、宾语、极性及原文位置 |
| 引号守卫只看句内字符，可能漏过多句引述的中间句 | `Mira said, "Lina sings. Nora dances. Ada reads."` | 引述覆盖的中间句同样保守拒绝；不因它本句没有引号就抽出独立断言。不配对、嵌套或命题引述仍不支持 |
| 跨查询的状态变化即可让阶段 A 通过 | 一个查询全缺失、另一个所有候选均 0 | 只检查同查询、可用数值间的区别；状态变化及 missing/0 不单独放行 |
| 没有区别的三种聚合仍进入比较；训练入口信任旧摘要 | 三臂候选分值完全相同，或仅有恒定偏移 | 要求聚合对比也随候选变化；开发检查完整池，训练再检查合法监督行。所有拟合之前重算，不接受旧版准入摘要 |

**版本隔离。** 默认 `subject_binding_basic_v1` 保持历史结果；新配置显式选择 `subject_binding_nominal_quotes_v2`，41 列新契约为 `candidate_difference_v3_en_subject_binding_v2`。新包另记 `extraction_rules`，列顺序、臂、英文基底、parser 与运行版本共同校验。相同列数不足以加载，v1/v2 模型或分数缓存互换会报错。两种规则共用原 token 缓存，但只接受已核实的原文摘要和冻结 token 生产契约；历史 `parser.extraction_rules=v1` 字段保留作为缓存来源标识，新提取规则单独记录，不把旧事实或旧分数当成新缓存。未重写冻结包，两个在线基线仍不使用 41 列。

正文词元匹配、主体身份、K≥2、复杂补语／被动等其余边界未放开。`not/never` 的极性保留，转述和意愿不当作事件已发生；没有引入同义词表、指代猜测、文本模型、召回或 BM25 修改。

**同输入比较。** Train 仍为 1,896 查询／269,941 完整池行，原 25 条缺池与 2 条冲突排除后 1,869 查询／3,738 监督行；开发仍为 76／10,465，74 查询共同覆盖。两种规则使用同一次加载所得的数据对象，来源隔离及历史 manifest 数量核对通过。原 v1 的全部 Train／开发结构、事实和逐候选分数与历史保存结果完全一致；英文 38 列缓存、历史 B／英文全池分数和排序、EM/E1/E2/E3 的 41 列矩阵及完整预测均精确重放。

| 机械结果 | Train v1 → v2 | 开发 v1 → v2 |
| --- | ---: | ---: |
| 查询结构支持数 | 242 → 244 / 1,896 | 10 → 10 / 76 |
| 可计算聚合的候选行 | 18,039 → 19,728 | 635 → 710 |
| 可用数值分布 | 0：18,026 → 19,715；0.5：13 → 13 | 635 个 0 → 710 个 0 |
| 新保留的事实记录／涉及不同段落 | 197 / 155 | 195 / 153 |
| 因跨句引述范围保守移出的旧事实／段落 | 5 / 3 | 5 / 3 |
| 全池中有数值区分的查询 | 7 → 7 | 0 → 0 |
| 合法指定两段中有数值区分的查询 | 0 → 0 | 0 → 0 |
| 同查询可形成聚合臂对比的查询 | 0 → 0 | 0 → 0 |

完整输出共享语料，Train 与开发的不同段落统计不能相加视为互不重叠样本。开发三种分数有 83 行发生 missing/0 状态切换，净增加 75 行可计算；不等于新增 83 次有效排序区分。`extraction_incomplete` 在开发全部行仍为 1。官方指定对的有限分差仍仅 4 条且全为 0，其余含缺失。

**既有人工结果未变。** v5 严格且共同覆盖的 52 条，仍为 46 查询被拒、3 两段无事实、3 两段均 0；全部指定对新增分数和状态不变。第 7 题两个 `received` 已通过引号检查，但后续分别被 `compound_or_qualified_subject`、`unresolved_pronoun_subject` 拒绝；第 11/48 题两段仍无事实。因此不能声称本次修复解决了人审可靠错例。详情见[人工范围机械重放](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/human-cohort-replay.json)。原官方和人审模型指标继续引用 §4 和 §2.8；没有新模型，不新增纠正／改坏或准确率数字。

预算在计算前记录为同 c3、种子 20260907、来源权重、最大 300 轮、耐心 40 的一次 E3/v1 控制与 E3/v2 对照，前提是修复版通过当前开发／监督训练准入。实际两处均因 `no_within_query_numeric_contrast` 未通过。此处终止的是依赖有效输入的拟合；不是缺少模型／数据，也不是工程修复未执行，更不宣称整个聚合方法无效。

**成本与过程。** 完整成功重放耗时 **58.18 s**，含两种规则、旧分数验证、写盘与模型重放；Train／开发的英文 38 列计算和文件装载为 45.47／1.77 s。两版正文缓存装载与提取：Train 0.625／0.543 s，开发 0.323／0.338 s；匹配为 Train 0.362／0.505 s、开发 0.011／0.058 s。这些局部计时不含查询提取与写盘，不能当作端到端延迟，计时波动也不是加速证据。NevIR 没有新 parser 推理，普通英文 15 例另用现有隔离 parser 环境执行；研究模型拟合为 0。首次比较在“v2 必须保留全部 v1 事实”的过严工程断言处中止，发现多句转述应允许保守移出旧记录后修正检查、补测试，并写入新 `comparison-v2/`；提取规则未据得分修改，第一次目录与日志保留，58.18 s 不含该次中止的成本。

**验收。** 修改前相关基线 **19 passed**；最终相关单元测试 **39 passed**，实际 parser 普通英文 **15/15**；完整非 integration **1,164 passed、3 deselected、6 既存 warnings，16.70 s**。覆盖标题／直弯引号、否定、跨句引述、破损引号、旧规则、错版本、缓存拒绝、两版模型保存重载一致，以及无信号时直接训练函数也不得调用 fitter。实际 CLI 验证旧摘要和新无信号摘要均在产生任何模型目录前报错。相关 Ruff、CLI 入口、文档链接、报告索引及 diff 检查见[验收记录](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/acceptance.json)。

配置：[v1](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/config-v1.json)／[v2](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/config-v2.json)；实际结果：[comparison-v2/results.json](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/comparison-v2/results.json)，包含准入、来源查询 ID、参数、成本及旧模型重放；全池分数、结构及事实变动位于同目录。工程中止见 `comparison/results.json`。完整回归原始日志为 [nonintegration-tests-final.log](../../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/nonintegration-tests-final.log)。

```bash
LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/python -m pytest -m 'not integration' -q
.venv/bin/python runs/post_recall/subject-binding-pilot-20260908/repair-20260909/compare.py --out-name 新目录名
.venv/bin/python scripts/subject_binding_development.py analyze \
  --config runs/post_recall/subject-binding-pilot-20260908/repair-20260909/config-v2.json \
  --cache runs/post_recall/subject-binding-pilot-20260908/parse-cache --out 新目录
```

**上一轮 PR #12 的独立验收（历史）。** 该次将修复相关代码／测试及本节记录从其他未提交修改中隔离，在基于 `origin/master` 的独立工作树验证。`PYTHONPATH=src LINKRAG_EVAL_REQUIRE_RAG=1 <现有环境>/bin/python -m pytest -m 'not integration' -q` 为 **1,146 passed、3 deselected、6 既有 warnings，16.22 s**；确认导入来自该工作树。七个相关 Python 文件 Ruff、两个 CLI `--help`、报告索引及 diff 检查通过。以上验证没有包含另行进行的人工收件／裁定修订。前述同输入机械比较、15 例实际 parser 检查和 58.18 s 成本来自原工作区已保存的修复运行，该次未重新训练或采集。`repair-20260909/` 中的配置、原始运行数据和日志按既有 runs 规则本地保存，不随该次源码提交。

### 3.5 版本覆盖、类型对称与事件保留的 v3 修复（2026-09-09）

负责人要求完成工程修复，不再仅放宽守卫后重算零分。本次依据实际工作区 `codex/nevir-human-review-20260909`、HEAD `5afd458b2e69695b99127a83d9ea6e6b183cc0ec` 执行，没有切到交接中提及的 `master 3e141b9`。原有人审源码、文档和未跟踪附件保留；没有提交、推送或替换当前两个工作模型。[执行记录](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/execution.json)记录范围，所有新结果进入 `representation-v3-20260909/`。

#### 实际修复与版本隔离

| 已核实缺口 | 实施内容 | 保留的限制 |
| --- | --- | --- |
| 训练入口依赖循环覆盖提取规则版本 | `extractor_version` 与 `expected_package_version` 分开；非空依赖字典的测试检查两次提取及保存状态实际收到的规则版本 | 不是历史全零的原因；本次真实训练经过非空依赖检查后成功拟合 |
| 查询含 `film` 类型条件、正文名词却没有相应类型证据 | 新版对查询与正文均保存名词类型记录，名词系表／同位说明采用同一表示 | 不删除查询类型；不能只凭事件相似就称全部满足 |
| 所有格、同位、并列或未知代词导致整条事件丢失 | 保存主体提及、原文位置、身份状态、类型、事件与参数；所有者是修饰信息；未知主体逐条隔离 | 本轮不推断代词前件；并列主语分配不明、被动或范围不明时保存为不确定，不提升为断言 |
| 参数整体词元相等，修饰与范围不可单独检查 | 参数拆出角色、中心词、修饰、原文跨度与范围；否定、情态、条件和引述单独记录 | `unfavorable`、额外限定等不删减；未解析查询限制仍阻止完整查询评分 |
| 匹配器只有布尔结果 | 新增可替换 `EvidenceMatcher`，返回 support／conflict／unknown 与正文证据；默认严格结构匹配 | `rave` 与 `favorable` 暂不认作同义；只在同结构显式极性相反时判 conflict，不擅自把未知判冲突 |
| 所有训练共用绑定准入 | `experiment_purpose=basic_matching` 只要求同查询有效数值差异；`binding` 还要求聚合间差异；开发全池和合法训练行都必须通过 | 状态变化、缺失与零之差不能放行；基本匹配只训练 E0／EM／E1，未启动 E2/E3 或打乱实验 |

可复用框架留在 `subject_binding.py`；新记录模块为 [subject_binding_records.py](../../src/linkrag_eval/retrieval/learning_to_rank/subject_binding_records.py)，匹配接口为 [subject_binding_matching.py](../../src/linkrag_eval/retrieval/learning_to_rank/subject_binding_matching.py)。没有复制 LTR 或新增通用插件平台。规则显式选择 `subject_binding_evidence_records_v3`，旧 v1 默认与 v2 不变。v3 离线模型绑定 `candidate_difference_v3_en_subject_binding_v3`、有序 41 列、`subject_event_evidence_v1` 和 `strict_structured_evidence_v1`；规则、匹配器、模型或缓存错配均拒绝。

复用的原 parser 缓存仅提供相同原文的 token／依存结果，其历史生产者契约仍带 v1 字段；没有把旧事实或分数冒充 v3。新事实、分数、41 列缓存与模型分别携带新身份。原 38 列核心和两个工作模型未改。

#### 原文贯通验收

[真实 parser 契约测试](../../tests/contract/test_subject_binding_parser.py)在已有隔离环境中，用原始普通英文调用 spaCy 3.8.16／en_core_web_sm 3.8.0，再经过当前提取、匹配和三个聚合，**23 项全部通过，0.54 秒**。不使用人工拼接三元组代替这一层测试。覆盖直接同表达、所有格／同位说明、已给前文和未给前文的代词、好评改述／差评／演员对象、额外修饰、显式否定、同对象／不同对象与跨句、引述／条件／并列不确定、未解析查询限制、替换接口及伪造证据拒绝、Unicode 位置和继承主语／情态证据。

普通英文中也发现了真实 parser 限制并原样留测：`Which scientist taught physics and studied chemistry?` 的 `studied` 被标作 `amod`；`Alice can teach physics and study chemistry.` 的 `study` 被标作名词。前者记录未解析条件，后者保留原始 token 证据，不捏造缺失事件。可正常解析的 emphatic `did study` 与 `can read and write` 另作正向样例，不能用这些通过项声称前述 parser 错误已修复。初次断言失败日志保留，没有改标签或按 NevIR 得分修补语法。

**旧行为回归与最终完整回归通过。** 同一开发输入的 v1/v2 查询结构、段落事实、全池分数和覆盖记录与各自历史产物完全一致；当前 B／英文全池重放与英文 38 列 NPZ 逐值一致。原模型重载、跨版本拒绝、缓存匹配器拒绝及入口准入测试通过。完整命令为 `LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/python -m pytest -m 'not integration' -q`，结果 **1,190 passed、3 deselected、6 既存 warnings，16.52 秒**，见[完整日志](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/full-nonintegration-delivery.log)。这证明工程行为与隔离，不等于人工核验了抽取语义准确率。

#### 原开发快照与合法训练行的准入

仍是 Train 1,896 查询／269,941 候选行，原排除后 1,869 查询／3,738 行／472 来源组进入损失；开发 76 查询／10,465 行，共同覆盖 74 查询／37 对／19 来源组。所有特征先用完整池计算，监督只取原合法指定候选，来源、权重、正文、切块、召回、BM25 均不变。

| 机械观察 | 前一阶段 v2 | 本次 v3 |
| --- | ---: | ---: |
| 开发可处理查询 / 76 | 10 | 22 |
| 开发可计算候选行 / 10,465 | 710 | 1,651 |
| 可计算值 | 全 0 | 1,625 行为 0；26 行为 0.5 |
| 开发全池有数值区分的查询 | 0 | 8 |
| 开发聚合之间有区分的查询 | 0 | 0 |
| 合法 Train 指定对有数值区分的查询 | 0 | 6 |
| 绑定比较准入 | 不通过 | 不通过 |

v3 开发 1,642 段保存 32,788 条记录，其中 24,004 条事件、8,784 条类型；30,022 条标为不确定，2,766 条可用，保留了 12,913 条身份未解事件。这是记录保留量，不是正确事实数。原 v2 只有 1,782 条可用词面事实，二者记录定义不同，不能直接算抽取准确率提升。76 条指定对中，15 条有限差值为 0、1 条为 +0.5、60 条缺失；唯一非零为原第 41 题。v5 人工比较的 52 题中有 13 条查询可处理，不代表 13 条都已解决。

Train 的全部候选评分为 233,804 行缺失、35,895 行为 0、233 行为 0.5、9 行为 1/3；三种聚合仍处处相同。基本匹配的两个门槛均通过，因而仅执行固定三臂；具体查询与结构计数见[表示审计](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/representation-audit.json)，完整准入见[实际训练结果](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/basic-training/results.json)。没有通过关闭准入开始拟合。

#### 固定三次拟合的实际结果

沿用原已选 c3、种子 20260907、来源平衡、最高 300 轮、早停 40 轮及同一开发来源宏平均选模规则；未扩网格或更换监督。E0 是英文 38 列控制；EM 是同两列状态标志加常零列；E1 是同标志加基础条件匹配分数。

| 实际模型 | 官方严格正确 / 74 | 逆序 | 同分 | 双向全对 / 37 | 来源宏平均 | 最佳轮／实际轮 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E0 | 44 | 29 | 1 | 9 | 60.53% | 67／107 |
| EM | 45 | 25 | 4 | 10 | 61.84% | 22／62 |
| E1 | 46 | 28 | 0 | 10 | 63.16% | 33／73 |

| 官方对照 | 共同正确 | 纠正 | 改坏 | 共同未正确 |
| --- | ---: | ---: | ---: | ---: |
| E0 → EM | 41 | 4 | 3 | 26 |
| E0 → E1 | 42 | 4 | 2 | 26 |
| EM → E1 | 43 | 3 | 2 | 26 |

**三个模型的完整开发预测分别与原 N08 对应模型完全相同；EM／E1 新增三列分裂数均为 0。** E0 模型精确复现英文基线。表中的 44→46 不是本次表示修复产生的新收益，也不能证明基础匹配或绑定有效。人工固定 v5 的 52 题重算为 E0 31 正确／21 逆序／0 同分，EM 32／18／2，E1 32／20／0；双向全对为 6／21、5／21、5／21，E0→E1 仍纠正 3、改坏 2。该关联复用原已核实私有映射和固定人工输入，未重标，见[人工敏感性](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/human-sensitivity.json)；它不是抽取金标，也不是独立确认。逐来源分布保存在上述两份结果中。

#### 成本、最终证据校正与复现入口

本地实测的数据准备 46.894 秒，其中 Train／开发原英文 38 列计算为 43.435／1.970 秒；段落 token 缓存读取与抽取累计为 2.355／1.877 秒；完整池匹配为 1.350／0.046 秒。缓存已存在，这些不是冷启动 parser 或在线端到端成本。E0 原选择函数记录总计 0.766 秒，完整池预测排序 0.0100 秒；EM／E1 含独立拟合进程分别 0.633／0.628 秒，完整池预测及排序 0.0074／0.0079 秒。不把各范围有重叠的时间相加。当前开发详细事实 JSONL 约 152 MiB，证据保留有明显磁盘成本，未据此主张部署可行性。

三次拟合后，验收发现继承主语／情态的记录应把继承词也纳入事件证据跨度，已作纯证据字段校正。拟合时的源码留在 `source-at-fit/`，原 spec、日志和模型不覆盖；当前 [config-v3-final.json](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json) 关联当前 spec。最终再次提取允许范围内的 1,968 个查询文本、1,761 个段落文本，逐行复算 **269,941＋10,465 行全部数值与拟合时精确相同**，耗时 8.643 秒、零追加拟合；见[最终重放](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/final-replay/checks.json)。证据校正没有被伪装成另一轮效果实验。

当前复现命令从项目根目录运行；以下输出目录须尚不存在，不能覆盖本次运行：

```bash
.venv/bin/python scripts/subject_binding_development.py analyze --config runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json --cache runs/post_recall/subject-binding-pilot-20260908/parse-cache --out runs/post_recall/subject-binding-pilot-20260908/representation-v3-replay-new
.venv/bin/python scripts/subject_binding_training.py train --config runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json --development-summary runs/post_recall/subject-binding-pilot-20260908/representation-v3-replay-new/summary.json --cache runs/post_recall/subject-binding-pilot-20260908/parse-cache --out runs/post_recall/subject-binding-pilot-20260908/representation-v3-training-new
```

实际新模型位于 `representation-v3-20260909/basic-training/E0/model-b`、`EM/model`、`E1/model`；都是本地实验产物。最终源文件、CLI 拒绝检查、旧模型重放、Ruff／文档／diff 验收见[交付验收](../../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/acceptance.json)。本轮工程修复完成，效果没有新增；不再原样重复拟合，不自动接入语义或指代模型，下一项候选见 §6。

## 4. 五组固定训练、对称结果和来源分布

复用 c3：学习率 0.03，叶子 7，深度 3，L2=1，列采样 0.8，种子 20260907，最多 300 轮，耐心 40；其余参数、来源权重、监督、原始特征与 N06 一致。来源宏平均严格正确率用于早停，保留最早最佳树前缀，不 refit、不增加网格。EM/E1/E2/E3 的前 40 列逐值一致。模型各写新目录；E0 为原英文契约，41 列离线包绑定臂和 parser／规则，不能进入旧 38 列在线路径。

| 模型 | 严格正确 / 74 | 逆序 | 同分 | 双向全对 / 37 | 来源宏平均 | 最佳树数 / 实跑轮数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 47 | 27 | 0 | 11 | 64.47% | 历史冻结 51 |
| E0 | 44 | 29 | 1 | 9 | 60.53% | 67 / 107 |
| EM | 45 | 25 | 4 | 10 | 61.84% | 22 / 62 |
| E1 | 46 | 28 | 0 | 10 | 63.16% | 33 / 73 |
| E2 | 46 | 28 | 0 | 10 | 63.16% | 33 / 73 |
| E3 | 46 | 28 | 0 | 10 | 63.16% | 33 / 73 |

纠正／改坏的“正确”按官方严格偏好；同分归入未严格正确。下面列全体 74 查询，不按可用性或成功筛样本。完整 19 来源组四格以及所有指定参照的比较在 [results.json](../../runs/post_recall/subject-binding-pilot-20260908/stage-b/results.json)。

| 参照 → 方法 | 共同正确 | 纠正 | 改坏 | 共同未正确 | 净增 |
| --- | ---: | ---: | ---: | ---: | ---: |
| E0 → EM | 41 | 4 | 3 | 26 | +1 |
| E0 → E1 | 42 | 4 | 2 | 26 | +2 |
| E0 → E2 | 42 | 4 | 2 | 26 | +2 |
| E0 → E3 | 42 | 4 | 2 | 26 | +2 |
| EM → E0 | 41 | 3 | 4 | 26 | -1 |
| EM → E1 | 43 | 3 | 2 | 26 | +1 |
| EM → E2 | 43 | 3 | 2 | 26 | +1 |
| EM → E3 | 43 | 3 | 2 | 26 | +1 |
| B → E0 | 39 | 5 | 8 | 22 | -3 |
| B → EM | 39 | 6 | 8 | 21 | -2 |
| B → E1 | 41 | 5 | 6 | 22 | -1 |
| B → E2 | 41 | 5 | 6 | 22 | -1 |
| B → E3 | 41 | 5 | 6 | 22 | -1 |

E3 相对 E1、E2 的纠正和改坏均为 0，全部分数／排序逐字节相同。自动可用子集仅 4 查询，所有臂均 2 正确、2 逆序、0 同分、0/2 双向全对；只是抽取可用子集，不是人工可判子集。

| 来源组（末四位） | 查询数 | 历史 B | E0 | EM | E1＝E2＝E3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0462 | 4 | 4 | 2 | 2 | 2 |
| 0468 | 4 | 2 | 2 | 2 | 2 |
| 0471 | 4 | 2 | 2 | 3 | 2 |
| 0473 | 4 | 2 | 2 | 2 | 2 |
| 0475 | 4 | 2 | 3 | 3 | 3 |
| 0476 | 4 | 3 | 1 | 2 | 2 |
| 0478 | 4 | 2 | 4 | 4 | 4 |
| 0479 | 4 | 3 | 2 | 2 | 2 |
| 0494 | 4 | 2 | 2 | 2 | 2 |
| 0504 | 4 | 3 | 3 | 3 | 3 |
| 0508 | 4 | 2 | 2 | 1 | 2 |
| 0516 | 4 | 3 | 3 | 3 | 3 |
| 0518 | 4 | 3 | 2 | 2 | 3 |
| 0533 | 4 | 2 | 2 | 2 | 2 |
| 0548 | 4 | 2 | 2 | 2 | 2 |
| 0557 | 2 | 2 | 2 | 2 | 2 |
| 0558 | 4 | 2 | 2 | 3 | 3 |
| 0561 | 4 | 3 | 3 | 3 | 3 |
| 0564 | 4 | 3 | 3 | 2 | 2 |

逐一去掉一个来源组后，E3 对 E0 的严格准确率点差范围为 +1.43 至 +4.29 个百分点；对 EM 为 0 至 +2.86；对历史 B 为 −4.29 至 +1.43；对 E1/E2 恒为 0。这里是来源敏感性描述，没有置信区间或独立验证含义。

**所有新增列实际分裂次数为 0。** 因此 E0→EM/E1 的小变化不能解释为模型利用了状态、词元匹配或主体连接。模型只使用原 38 列；增加列时仍固定列采样比例和种子，并不保证相同训练路径，且最佳轮数不同。维数、列采样和早停变化的贡献没有被本轮另行分离，不能把它们计为语义收益。未为追查这点追加拟合。见[机器验收](../../runs/post_recall/subject-binding-pilot-20260908/checks/postrun-acceptance.json)。

阶段 C 未触发：E3 未超过 E1/E2 或历史 B，相对 E1/E2 没有正向变化。三个预定主体置换种子均未运行，不记为“打乱无效”或“零损失”。

## 5. 成本、技术验收与执行入口

硬件 Apple M5、10 CPU 核、16 GiB 内存，macOS arm64；原训练 Python 3.11.15、LightGBM 4.7.0、NumPy 2.4.6、scikit-learn 1.9.0。parser 与 LTR 使用单进程／单线程设置；未实测线上并发、端到端服务延迟或费用。

| 计时范围 | 本地实际时间 |
| --- | ---: |
| 隔离环境创建＋依赖／模型安装（下载未单独计时） | 9.28 s |
| 首次构造解析进程初始化 | 21.90 s |
| 开发 parser 初始化 | 0.550 s |
| 开发正文首次解析 1,642 段 | 15.071 s |
| 开发查询解析 76 条 | 0.114 s |
| Train parser 初始化 | 0.538 s |
| Train 新正文解析 119 段（另 1,642 缓存命中） | 0.923 s |
| Train 查询解析 1,892 个不同文本 | 2.647 s |
| 一轮完整池英文 38 列计算：Train / 开发 | 44.188 / 1.681 s |
| 新分数匹配：全部 Train 池 / 全部开发池 | 0.442 / 0.010 s |
| 正文 token 缓存读取＋规则提取：Train / 开发 | 0.889 / 0.406 s |

匹配计时已解析后的逐 query 完整池计算，不包含 parser、文件装载、LTR 特征或模型预测；详细逐 query 计时在各 signals 目录。正文字符长度：开发 94–1,298，中位 703；Train 不同正文 94–1,298，中位 694。完整读取，没有默认截断。缓存总计 39,198,258 字节（包括构造探针）；parser 进程峰值 RSS 约 165.7–173.8 MB，不是整台机器或 LTR 的峰值内存。初次模型准备、OS 缓存和后续热启动的计时不能混为同一种延迟。

| 训练臂 | 原生 fit＋最佳前缀检查 | 带子进程启动的 fit | 全开发池预测＋排序 |
| --- | ---: | ---: | ---: |
| E0 | 0.0838 s | 训练导出总计 0.7669 s | 0.0102 s |
| EM | 0.0455 s | 0.6754 s | 0.0080 s |
| E1 | 0.0503 s | 0.6521 s | 0.0083 s |
| E2 | 0.0411 s | 0.6541 s | 0.0084 s |
| E3 | 0.0408 s | 0.6601 s | 0.0082 s |

E0 的外层耗时还含导出和预测，与其余臂的“仅 fit 外层”不完全同范围；各臂实际 history／fit／selection 保留原计时字段。解析缓存热命中只复用完全一致原文，背景语料跨池共享不等于使用开发监督训练。

验收记录位于 [checks](../../runs/post_recall/subject-binding-pilot-20260908/checks/)：

- 原 B／英文全池重放、英文缓存逐值一致；E0 原模型文本逐字节复现；五臂导出重载预测一致。
- 核心、Unicode、正反语法、对象／宾语／极性／情态、缺失、置换守恒、版本错配及包／收件防串验证通过；人工收件测试只用合成样例，未写真实人类意见。
- 完整非 integration 命令：`LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/python -m pytest -q -m 'not integration'`。最终结果见下方验收更新及日志。
- 本轮相关 Python 文件 Ruff、CLI `--help`、本地文档链接、报告索引和 `git diff --check` 的最终状态见下方验收更新。
- 该次技术交付未完成实际浏览器 UI 验收；原因见 §2。当时人工复核／裁定尚未完成，后续接收与敏感性分析见 §2.7；浏览器实测和抽取准确率未由该分析补齐。

重现使用 [config.json](../../runs/post_recall/subject-binding-pilot-20260908/config.json)中的显式输入，依次为：开发 `prepare` → 独立 parser → 开发 `analyze` → Train `prepare-texts` → 独立 parser → `train`。每次必须指定新的输出目录，脚本拒绝覆盖旧产物；不自动运行确认或 Test。[脚本入口](../../scripts/README.md)列出各 CLI。

程序性修正记录：初始运行元数据曾由旧系统 Python 调用而失败，改用原 `.venv` 后继续；冻结前语法修正见 §3.1；训练后仅补显式英文基底校验、收件校验及测试，没有改已冻结提取公式、重算模型权重或重试训练。首轮全回归 1,080 passed／3 deselected／7 warnings，其中新增合成模型测试的数组切片提示随后通过复制测试标签消除；原始日志保留，最终回归另存。没有拟合失败或额外模型重试。

### 5.1 最终交付验收

最终完整非 integration 回归为 **1,081 passed、3 deselected、6 warnings，10.47 s**（精确用时以[原始日志](../../runs/post_recall/subject-binding-pilot-20260908/checks/full-regression-delivery.log)为准）；6 项为既有 SWIG／LightGBM 弃用提示，没有新增失败。增加了部分人工表单缺字段仍能生成待补充清单的回归样例，未将缺字段补为判断。

14 个相关 Python 文件 Ruff 通过；六个 CLI 的 `--help` 均成功；11 份受影响文档的 352 个本地链接均有目标，报告索引校验通过。首次 diff 检查发现 `scripts/README.md` 多一个末尾空行，已删除并复查通过。详情见 [ruff-delivery.log](../../runs/post_recall/subject-binding-pilot-20260908/checks/ruff-delivery.log)、[cli-help.json](../../runs/post_recall/subject-binding-pilot-20260908/checks/cli-help.json)、[document-links.json](../../runs/post_recall/subject-binding-pilot-20260908/checks/document-links.json)。

本轮新增 12 个 Python 文件，共 1,847 行（含三个单元测试文件）；既有数值核心仅共享 fitter 的列名／宽度检查改动。唯一新增正式报告就是本文件，计划、进度与台账沿用旧入口。具体文件见[变更记录](../../runs/post_recall/subject-binding-pilot-20260908/checks/delivery-change-summary.json)；Git 未提交、未推送，原有未提交内容保留。

## 6. 唯一下一步：局部改述的支持判断对照

版本传递、类型对称、事件与证据保留的工程修复已经交付。继续使用现有英文基线；本次新增匹配列没有被树使用，不再原样重复训练，也不把三种相同聚合的比较当作绑定有效性证据。

下一项仅建议利用已建立的 support／conflict／unknown 接口，设计一个有明确正反样例的局部改述支持判断对照：例如好评改述应能支持，同时差评、对象替换和额外限制不能误支持。该候选尚未接入或执行，不能预先承诺解决 NevIR；它与本次已完成的工程修复分开。没有恢复 Qwen/BGE、指代模型、重新召回、修改 BM25 或使用确认／Test。
