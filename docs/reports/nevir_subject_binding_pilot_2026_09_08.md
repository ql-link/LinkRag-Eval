# NevIR：自动事实条件聚合与独立盲审交付（2026-09-08）

**结论：本原型未成功检验“同主体绑定带来增量”的假设，停止本轮方法扩展。** E0 复现英文基线 44/74；EM 为 45/74，E1/E2/E3 均为 46/74，三者完整候选预测逐字节相同，低于历史 B 的 47/74。更关键的是，三项聚合分数在 Train／开发全部候选上相同，所有新增列在最终树中的分裂次数均为 0。不能将 44→46 解释为绑定能力增强，也不能据此否定其他关系方法。

本报告为台账 **N08** 的唯一正式实证记录。设计维护于[研究计划 §2.7](../plans/post-recall-research-plan.md#27-同一自动事实上的条件聚合对照2026-09-08)，当前进度维护于[CURRENT_STATUS](../CURRENT_STATUS.md)。官方标签探索已完成；人类提交 **0/2**、裁定未开始、提取语义准确率与可靠纠错均 **pending**。不进行独立确认或 Test 评分。

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

**当前分发使用 §2.3 的 `handoff-structured-v2` 两份 ZIP。** 下方初版、§2.1 和 §2.2 保留各自版本的交付事实，均不再作为当前分发入口。

- [reviewer_1_package.zip](../../runs/post_recall/subject-binding-pilot-20260908/handoff/reviewer_1_package.zip)
- [reviewer_2_package.zip](../../runs/post_recall/subject-binding-pilot-20260908/handoff/reviewer_2_package.zip)

每份只有该人的 `review.html`、`cases.jsonl`、`blank-answers.jsonl` 和同一份中性 `README.md`。原三份公共文件逐字节复制 N05；两人各自的 76 查询、152 个正文展示、匿名编号、顺序、X/Y 位置与原私有映射逐项一致。没有重新抽样、打乱、生成编号或把缺失目标加入候选。ZIP 成员白名单、CRC 和解包字节通过，公共材料没有私有映射、官方方向、模型结果或另一人的意见。详见[分发 manifest](../../runs/post_recall/subject-binding-pilot-20260908/handoff/handoff-manifest.json)，该 manifest 属于研究侧，**不随 ZIP 分发**。

使用方式：分别解压自己的一份，先读 README，用桌面浏览器打开 `review.html`；姓名可用稳定代号，类型选人类，每人完成全部 76 条。选择 X/Y 原文证据、填写适用性与理由，保存后点击“下载结果”。交回各自完整 `reviewer_1-answers.json`／`reviewer_2-answers.json` 原文件，不能只交截图。最初页面以原打开位置的浏览器本地存储恢复草稿，当时没有 JSON 导入功能；新版已补齐（见 §2.1），仍应频繁下载备份。file 访问有问题时，README 给出只暴露自己公共目录的本机 localhost 方法。

**验收限制：**自动浏览器打开 file URL 被 Browser URL security policy 拒绝，未尝试其他入口绕过。因此没有实际浏览器中的视觉、保存恢复或下载验收。已有页面的 Node 模拟 DOM 测试覆盖保存、恢复、导出和 Unicode 摘录校验，公共文件与该受测 renderer 完全一致；这不等于实际浏览器验收。

收件入口已经用纯合成测试验证，但尚未用于真实提交：

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

两人通过原私有映射对齐，不按第几题或 X/Y 直接对齐；分歧材料保留两份判断和原文，仍不显示官方／模型结果。选项相同也需人类核对理由是否冲突；程序不投票、不解释分歧、不产生金标。人工裁定须带身份、时间、版本；负责人锁定并保存摘要后才关联本轮已保存模型结果，追加本报告的敏感性评价，不重训、不改官方统计。现在未创建假收件或假裁定；没有人类判断，所以锁定后分析尚未执行。

### 2.1 分发页面持久化修订（2026-09-08，侧栏请求）

负责人要求补强独立标注员的保存可靠性。**该次持久化修订曾分发[审阅者 1 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/reviewer_1_package.zip)和[审阅者 2 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/reviewer_2_package.zip)。** 上述旧包记录保留供追溯；旧 ZIP、N05 页面、正文、编号、顺序与私有映射没有覆盖。新版 `cases.jsonl`、空白模板以及页面内嵌数据／存储键与原版一致。

新增输入即时自动保存、明确保存失败提示、未下载备份的离开提醒、带时间的 JSON 备份、JSON 导入续填。未完成或证据位置暂时不一致的原始字段也作为草稿保存；本地存储报错时仍可下载备份或结果。导入检查包、正文版本、匿名编号、证据和字段；替换已有草稿需确认并先发起现有备份下载，错误／取消不替换。其他窗口修改同一草稿时停止覆盖保存并提示备份。

保存只是当前浏览器的本地副本；每次结束仍须下载 JSON 并确认文件实际存在。没有服务器或后台自动上传，无法承诺设备损坏、清理数据或未完成下载后也绝不丢失。新版 README 已明确这些边界及恢复步骤。普通答案导出维持 schema_version=1，附带可恢复草稿；已有收件检查可接受，不改人类判断或模型结果。

实现：[review_persistence.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_persistence.py)；通过 16 项新增持久化用例及既有页面／收件回归，共 **64 passed**。两个实际新版包分别进行了 76 条临时草稿的 JS 导出／导入逐值检查，内容和私有标识隔离校验通过。测试仅在 Node 模拟环境执行，没有写真实人工提交；**真实浏览器验收仍未执行**。[验收记录](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/acceptance.json)与[测试日志](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/tests.log)保留。该次版本的收件 manifest 为 `handoff-durable-v1/handoff-manifest.json`；当前新版入口见 §2.3，仍连接原 N05 私有映射。

**学生入门页补充。** 根据负责人的侧栏请求，两份新版 ZIP 均加入相同的独立[标注入门.html](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/reviewer_1/标注入门.html)：三个自编讲解示例、三道先填后看参考标注的练习。面向非专业学生说明四种适用性、查询歧义、相对偏好和证据理由；仅展示参考，不比较选项、不评分。六道材料均非 NevIR 正式样本，也不进入人工金标或模型实验。练习使用独立本地存储，不能改动正式 76 条；两份教程与说明一致。原 `review.html`、cases 和空白模板字节不变，之前分发的 ZIP 已保存到 `handoff-durable-v1/archive-before-tutorial/`。离线脚本检查了三题填写门槛、参考初始隐藏、展示后保留作答、刷新恢复、清空隔离以及存储失败时仍可练习；[检查记录](../../runs/post_recall/subject-binding-pilot-20260908/handoff-durable-v1/tutorial-checks.json)保留，未进行真实浏览器视觉验收。

### 2.2 主会话独立验收：填写后能否用于正式收件

**通过：该次验收的两份 durable-v1 包中完整、合规填写后导出的最终 JSON，可以按对应旧版 manifest 收件。** 当前结构化版的验收见 §2.3。 这里确认数据链路与程序契约，不保证任意浏览器／设备上绝不丢失，也不把填写完整当作语义正确。

本次直接读取 `handoff-durable-v1` 两个实际 ZIP 内的页面脚本，以包含真实 HTML 控件、真实 select 选项及事件的 DOM 模拟逐题填写，而非只构造后端 JSON。每份 76 条都走过逐输入自动保存、仅凭本地存储刷新恢复、备份／最终导出、空白存储环境导入再导出；恢复结果逐值一致。之后实际调用 `receive_submission`，两份均 76/76 完整、零格式／身份／Unicode 证据错误，原文件只读副本逐字节相同。

这批程序生成文件的身份与理由明确标记 QA ONLY，原始、规范化及待裁定文件只放独立系统临时目录，没有作为人类结果、训练或语义证据；当前仍 **0/2 人类提交**。用原私有映射核对全部 76 条，正确处理审阅者 2 的 40 条 X/Y 互换，准确得到预设 7 条 QA 分歧；没有自动锁定判断或关联模型。

验收查实并修复：

1. 新版导出的 `storage_key` 已绑定原正文与匿名顺序，后端此前忽略它；新增错版本拒绝检查，原始无此字段的导出明确记录为 legacy。失败复现见 [version-mismatch-before.log](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/version-mismatch-before.log)。关联阶段还须核对收件所用分发包版本，防止错误 manifest 混用。
2. 对齐后两人的选项已转换为统一 X/Y，但原始理由中的字母不能自动改写。现保留每人的原 case ID、原选项、原段落标记及原 X/Y → 统一 X/Y 的说明，避免把第二人的原 X 理解成第一人的 X；理由本身不改写。
3. 即使查询歧义字段和相对偏好未选不确定，只要单段判断为“无法裁定”，也加入人类不确定清单；仍不替人裁定。

教程的 21 个真实必填控件（3 题）逐项检查通过：未填完或选项不合法时参考区保持隐藏；全部完成后只展示参考，不评分；刷新恢复填写和展示状态；取消重置不改记录，确认重置不动正式存储键；本地存储失败仍可练习。另用含 emoji 的独立单元样例验证选择证据的 Unicode 字符偏移，未将 emoji 填入正式正文。

**限制仍明确：没有真实浏览器渲染、磁盘下载或跨 Chrome／Firefox 的现场验收。** 前次 file URL 导航被 Browser URL security policy 拒绝，本次未绕过。空白 DOM 存储环境导入不是实际换浏览器，模拟 Range 也不是原生鼠标选中文字。审阅者仍应按 README 确认 JSON 已实际下载到磁盘。

相关回归 **67 passed**；完整非 integration **1100 passed、3 deselected、6 warnings，12.02 s**；五个相关源码／测试文件 Ruff 通过。详见[本次验收](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/acceptance.json)、[端到端记录](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/packet-end-to-end.json)、[相关测试](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/related-tests.log)、[完整回归](../../runs/post_recall/subject-binding-pilot-20260908/handoff-final-acceptance/full-regression.log)。

没有修改 ZIP 内材料，两个实际分发包的 SHA 与本次验收前相同，仍各含 5 个公共文件；正文、编号、顺序、教程及旧包均保留。本次仅修正式收件／对齐程序、补测试及记录，没有重训、召回或读取确认／Test 逐题。

### 2.3 结构化原因选择：当前分发与收件契约

负责人经侧栏明确要求降低重复自由文字负担。本次同步修改正式页面、教程、草稿／备份／导出、接收／对齐程序与文档；只调整审阅工具，没有新模型实验。**当前分发：[审阅者 1 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/reviewer_1_package.zip)、[审阅者 2 ZIP](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/reviewer_2_package.zip)。每人独立完成全部 76 条。**

| 保留或新增 | 具体规则 |
| --- | --- |
| 保留四种适用性、歧义、相对偏好、复核状态 | 选项和含义沿用；程序不会从原因选项推导偏好或相关性 |
| 每段必填多选依据 | 人物对象、行为关系、肯定否定、时间数量比较、缺少信息、歧义矛盾、其他／说不清。类型描述审阅者所用证据，不是模型机制标签 |
| 条件摘录 | 支持／明确不满足必须给逐字原文与 Unicode 位置；证据不足／无法裁定可以无摘录 |
| 条件补充 | 证据不足要选具体缺失内容类型或写短注，只选缺少信息不完整；无法裁定或选择其他必须短注。普通清楚情况可留空 |
| 比较依据 | 8 个固定选项覆盖单段优势、双方支持／不足／不满足、质量差异、歧义和其他；特殊比较或不确定时写短注。相对偏好独立保存，绝不按原因码改写 |
| 教学 | 3 自编讲解＋3 独立练习，全部条件字段齐全后才显示参考，不计分。与正式页共用原因契约和条件检查；练习独立保存，不写正式结果 |

**字段入门说明补充。** 两份当前 ZIP 的教程已在示例前增加字段说明表，逐项解释身份、查询歧义、适用性、原因类别、摘录与自动位置、补充说明、相对偏好、比较依据和复核状态，明确四类适用性及“无严格优劣／无法裁定”的区别，并说明保存与交回。仅新增教学文字与表格样式；正式页、正文、空白模板、README、教程脚本及内嵌练习数据均保持字节一致，现有草稿和字段规则不变。更新前 ZIP 与 manifest 保存在当前分发目录的 `archive-before-field-guide/`，当前 manifest 已更新教程与 ZIP 摘要。相关回归 **93 passed**，Ruff 与 diff 检查通过，两包成员／CRC／摘要一致；见[补充验收](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/field-guide-checks.json)。未新增真实浏览器验收或人类判断。

新答案头 `schema_version=2`、`reason_schema_version=structured_reasons_v1`；单题带 `answer_schema_version=2`，新增 `pair_reason_code`，每段新增 `reason_types`。`reason`／`pair_reason` 仍原文保存，仅按上表条件必填。公共 `cases.jsonl` 与 N05 原文件逐字节一致，正文、匿名编号、X/Y 位置和顺序未变；空白模板升级结构，所有新选择为空。两份 ZIP 各含五个公共文件，不含研究侧 manifest、private 映射、官方方向、模型结果或另一人的意见。

新草稿键为原正文绑定键加 `-structured-v2`。旧格式 1 的本地草稿和 JSON 可恢复原文字与证据，新类别保持空并提示逐题补填，不从文字自动打标签。即时备份也统一使用新格式，格式错误的原始字段仍以草稿保留。旧键、旧包及旧提交不覆盖；新版 manifest 下收到旧答案会保留原文件并报告版本不符，须由审阅者导入补填后再导出，不静默当成本版完整结果。旧格式只有使用其原 manifest 才按原必填条件校验。

接收分别检查格式版本、正文键、枚举、重复原因、条件字段、匿名 ID 和 Unicode 摘录；合规普通题可以不写自由理由。规范化结果保留真实选择，统计仅是多选频数，不视为语义真值。对齐继续使用原私有映射并保留每人原 X/Y 文字语境；新增原因类型差异作为单独待人工查看项，既不自动解释，也不将选项一致当作正确。人类提交仍 **0/2**，没有生成正式人工收件／金标，锁定后模型关联仍待执行。

实现职责：[review_schema.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_schema.py)定义固定枚举与条件，[review_structured.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_structured.py)仅升级和打包已核对材料，[review_tutorial.py](../../src/linkrag_eval/retrieval/learning_to_rank/review_tutorial.py)生成同契约教学页；复用已有持久化和接收模块，不新建平台。生成入口与收件命令见[脚本说明](../../scripts/README.md#n08-离线原型与人类收件)。

**实际验收：相关 93 passed；完整非 integration 1126 passed、3 deselected、6 warnings（15.82 秒）。** 规则条件的 1,536 种组合在 Python 与共享 JS 上一致；两份最终 ZIP 内实际脚本各完整填写 76 条，覆盖四种适用性、七种依据和八种比较选项，自动保存／刷新／备份／最终导出／空存储导入逐值相同，实际 Python 收件均 76/76 完整、零错误，原文件只读字节保留。原映射准确处理 40 条 X/Y 互换及 7 条预设 QA 分歧，无自动裁定或模型关联。旧实际 ZIP 导出的迁移、缺新增字段提示、旧键保留、跨包／正文／格式拒绝、本地存储失败备份，以及两份最终教程的条件解锁／恢复／清空隔离均通过。含 emoji 的单元样例验证按 Unicode 字符而非 UTF-16 单元计位置；未改正式正文。

程序生成的答案与收件只在独立系统临时 QA 目录，不进入研究标签、语义准确率或效果统计。**真实浏览器渲染、原生选文、磁盘下载及跨浏览器现场验收仍未执行**：此前 Browser URL security policy 拒绝继续有效，没有改走其他入口绕过。这里通过的是最终 HTML 的 DOM 模拟和真实 Python 数据链路；审阅者仍需确认 JSON 实际下载成功。

产物：[分发 manifest](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/handoff-manifest.json)仅供研究侧，[验收](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-audit/acceptance.json)、[最终包链路记录](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-audit/packet-end-to-end.json)、[相关测试](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-audit/related-tests.log)、[完整回归](../../runs/post_recall/subject-binding-pilot-20260908/handoff-structured-audit/full-regression.log)。旧包保留，未新增训练、召回、确认／Test 读取；N08 的官方探索结论不变。

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
- 唯一未完成技术项是实际浏览器 UI 验收；原因见 §2。人工语义复核／裁定未完成属于证据缺口，不是假定实验失败。

重现使用 [config.json](../../runs/post_recall/subject-binding-pilot-20260908/config.json)中的显式输入，依次为：开发 `prepare` → 独立 parser → 开发 `analyze` → Train `prepare-texts` → 独立 parser → `train`。每次必须指定新的输出目录，脚本拒绝覆盖旧产物；不自动运行确认或 Test。[脚本入口](../../scripts/README.md)列出各 CLI。

程序性修正记录：初始运行元数据曾由旧系统 Python 调用而失败，改用原 `.venv` 后继续；冻结前语法修正见 §3.1；训练后仅补显式英文基底校验、收件校验及测试，没有改已冻结提取公式、重算模型权重或重试训练。首轮全回归 1,080 passed／3 deselected／7 warnings，其中新增合成模型测试的数组切片提示随后通过复制测试标签消除；原始日志保留，最终回归另存。没有拟合失败或额外模型重试。

### 5.1 最终交付验收

最终完整非 integration 回归为 **1,081 passed、3 deselected、6 warnings，10.47 s**（精确用时以[原始日志](../../runs/post_recall/subject-binding-pilot-20260908/checks/full-regression-delivery.log)为准）；6 项为既有 SWIG／LightGBM 弃用提示，没有新增失败。增加了部分人工表单缺字段仍能生成待补充清单的回归样例，未将缺字段补为判断。

14 个相关 Python 文件 Ruff 通过；六个 CLI 的 `--help` 均成功；11 份受影响文档的 352 个本地链接均有目标，报告索引校验通过。首次 diff 检查发现 `scripts/README.md` 多一个末尾空行，已删除并复查通过。详情见 [ruff-delivery.log](../../runs/post_recall/subject-binding-pilot-20260908/checks/ruff-delivery.log)、[cli-help.json](../../runs/post_recall/subject-binding-pilot-20260908/checks/cli-help.json)、[document-links.json](../../runs/post_recall/subject-binding-pilot-20260908/checks/document-links.json)。

本轮新增 12 个 Python 文件，共 1,847 行（含三个单元测试文件）；既有数值核心仅共享 fitter 的列名／宽度检查改动。唯一新增正式报告就是本文件，计划、进度与台账沿用旧入口。具体文件见[变更记录](../../runs/post_recall/subject-binding-pilot-20260908/checks/delivery-change-summary.json)；Git 未提交、未推送，原有未提交内容保留。

## 6. 唯一下一步与人工续接

选择附件中的 **“原型未覆盖真实问题”**：当前受限自动抽取没有产生三种聚合之间的任何真实输入差异，监督行也没有可用数值分差；本轮无法有效检验绑定机制。停止当前规则的扩展、模型叠加和新确认。

**下一步只完成已分发 76 条的独立人工复核与裁定。** 结果回来后保留原始版本，通过原私有映射关联，形成中性人类分歧清单；人类锁定后，把这些判断与本轮已经保存的结构、事实及分数关联，更新本报告。人工未覆盖的提取准确性继续写“未核验”。不重抽、不重新训练，不根据方法输赢回改标签。若要提出下一版方法，必须先据该人工证据另行明确缺口，不在本轮自动启动。

官方标签结果只是已经曝光的开发材料上的探索。未证明可靠语义错误被修复、自然业务收益、最终答案质量或独立验证成功。
