# master 代码与文档联合审查（2026-09-13）


## 归档位置与使用（2026-09-13 整理）

本记录从 `.handoff/audits/master-20260913/` 迁入正式工程审查目录，供后续核实和修复引用。公开归档仅保留工程审查材料；写作相关编译记录和原始链接候选清单仅在本地保存，本文对应检查细节不公开。下文审查对象、计数、Issue 状态及 `recorded_not_implemented` 均描述原审查时点 `a6e2cc7`；本次只归档，没有重新执行审查或修复问题。源码链接改为仓库相对路径，标签中的行号仍是原审查定位，后续代码变化时以原提交追溯。

| 位置 | 内容与使用范围 |
| --- | --- |
| 本 README | 15 项发现、依据、影响边界及当时检查结果；后续补充或处理结论追加到对应条目 |
| [findings.json](findings.json) | 原审查的机器清单，保留原工作区路径和原时点状态，不充当自动更新的任务数据库 |
| [reproduce/](reproduce/) | 原合成复现与链接检查脚本，正文未改；保留当时的绝对路径和输出设置，不能视为任意目录下即用的现行 CLI |
| [evidence/](evidence/) | 原数值复现、环境、聚合核验、静态检查、构建与测试记录；原字节保留，绝对路径和 Issue 状态只作历史证据 |

脚本对应关系：`core-reproduce.py` 对应 C01–C04 的 `core-evidence.json`；`experiment-repro.py` 对应 C05–C07 的 `experiment-reproductions.json`；`check_links.py` 对应仅在本地保存的原始链接候选清单，最终问题以正文人工核实结果为准。C08/C09 保存了 `golden-rewrite-reproductions.json`，本批归档未包含对应独立脚本，不补造原复现入口。若需再次运行，先将脚本复制到独立临时目录并设置待核验源码及输出位置；保存结果不会因归档而重跑或覆盖。

早期 Qwen 的 8 份原始会话属于另一项研究证据，已按原字节迁入 [#14–#16 交接恢复目录](../../../runs/post_recall/open-judge-selection-20260911/README.md)，没有混入本次工程审查。原分支切换记录已完成核对和清理，处理范围见[存放总览 §7](../../WORKSPACE_MAP.md#handoff-organization)。

> 2026-09-14 后续核查与文档修订见[追加记录](#followup-20260914)。原 15 项清单、原证据和原时点状态保留；当前进度不再从末尾的历史未实施状态推断。

## Material Passport

| 项目 | 记录 |
| --- | --- |
| 用户要求 | 拉取并切换最新origin/master，全面检查代码与文档；只记录问题，不实施修复。 |
| 审查版本 | `a6e2cc7019c9204bb0ccf7ac64051c41afa81342`，含已合并#45；收尾再次核对远端master未变。 |
| 检查工作区 | `/Users/kawauso/Documents/Projects/LinkRag-Eval-issue22-completion`，分支master与origin/master一致。 |
| 原项目目录 | `/Users/kawauso/Documents/Projects/LinkRag-Eval`保留原分支、已暂存／未暂存改动及本地产物；未stash、reset或覆盖。只在其`.handoff/audits/`新增本审查记录。 |
| 方法 | 主代理与三个审查代理并行；静态审阅、离线测试、临时合成复现、跟踪聚合的算术核查。 |
| 验证身份 | 已报告代码行为经合成复现确认；科研结果为ANALYZED，只核对既有聚合和解释，没有重跑模型或来源组区间。 |
| 变更范围 | 未修改应用源码、现有工程／科研文档、模型、原始数据和实验结果；未commit/push/改issue，未连接GPU或真实数据库。 |

## 审查结论

记录 **15项：2项P1、10项P2、3项P3**。P1为值得优先处理的运行安全／结果保存风险，P2为确定的行为或复现说明问题，P3为解释与导航同步问题；优先级是供负责人决策的建议，不构成实施授权。

已检查的#18–#23现行评价链路和本次核对的聚合未发现新的计算错误。不能据本次工程缺陷推断已完成实验全部失效；也不能把“测试通过”当成这些入口没有缺陷。尤其BM25权重应核清实际运行口径，后续修复会改变召回分数时必须保留旧候选及实验身份。

## 已运行检查

| 检查 | 结果与限制 |
| --- | --- |
| 完整非integration测试 | **1,320 passed / 23 skipped / 3 deselected**，16.91秒，6个依赖既存warnings；要求真实rag包可导入。没有将23项skip写为通过。 |
| 两个标注／探针专项 | **40 passed**，0.47秒（#21与#22分别20项）。 |
| 依赖边界 | 源码扫描测试包含在上表；lint-imports退出0，但自身配置为0个contract，不将其视为独立边界证明。 |
| Python包 | wheel构建成功；从该wheel导入实际包并运行CLI --help成功，未使用原工作区editable代码冒充wheel。 |
| 语法／格式解析 | 跟踪的346个Python、88个JSON、17个shell全部解析通过。 |
| Ruff | 0.16.2按仓库配置扫346个跟踪Python，**248条告警**，其中32条来自`.ai`工具；项目部分216条。主要是存量风格／现代化问题，未执行fix，也不将216条逐条列为功能Bug。 |
| 报告索引 | build_report_index.py --check通过，未改写索引。 |
| 文档链接 | 93份非vendor Markdown、1,304个本地链接；429个链接目标仅在原项目工作区存在，按已披露的本地产物处理。人工核实后问题见D06。163个外链未逐一做可用性检测。 |
| 聚合算术 | 28份跟踪聚合、724组计数／准确率恒等式检查，0不一致；#20–#22报告对应数字核对一致。不是逐题评分复算或新效果实验。 |
| 统计解释 | 11项常见解释偏差清单已检查；来源依赖、失败保留、样本选择和推广限制中已明确披露的事项未重复报Bug。D04作为历史解释同步项。 |
| GitHub任务状态 | #14–#24均已关闭；#25论文、#26复现包、#27清理仍开放。本次未修改任何issue。 |

检查使用Python3.11.15；生产依赖安装记录为固定SHA `861f24810c3482ec0d86768a24f952b1e08ae675`。通过PYTHONPATH明确指向审查master的src。详细环境与日志在[evidence/](evidence/)。

## 待负责人决定的清单

| ID | 级别 | 问题 | 定位 |
| --- | --- | --- | --- |
| C01 | P1 | 普通 run 会覆盖旧结果，同名基线变成自比 | [src/linkrag_eval/cli.py:803](../../../src/linkrag_eval/cli.py) |
| C02 | P1 | Alembic 环境变量入口绕过本地 SQLite 护栏 | [alembic/env.py:30](../../../alembic/env.py) |
| C03 | P2 | SQLite BM25 的 coarse/fine 权重未应用到正文列 | [src/linkrag_eval/store/sqlite_bm25.py:264](../../../src/linkrag_eval/store/sqlite_bm25.py) |
| C04 | P2 | 普通 ingest 耗尽重试后仍以成功退出 | [src/linkrag_eval/app.py:97](../../../src/linkrag_eval/app.py) |
| C05 | P2 | 候选缓存恢复会静默保留旧标签 | [src/linkrag_eval/retrieval/learning_to_rank/cache.py:78](../../../src/linkrag_eval/retrieval/learning_to_rank/cache.py) |
| C06 | P2 | MAP 的分母随实际返回长度缩小，漏召回也可得满分 | [src/linkrag_eval/metrics/retrieval.py:220](../../../src/linkrag_eval/metrics/retrieval.py) |
| C07 | P2 | 参考无标题或图片时，产物新增元素被记为零误检 | [src/linkrag_eval/metrics/cleaning.py:230](../../../src/linkrag_eval/metrics/cleaning.py) |
| C08 | P2 | 改写缓存未校验模型和提示版本，却报告为当前模型 | [src/linkrag_eval/query_rewrite/planner.py:124](../../../src/linkrag_eval/query_rewrite/planner.py) |
| C09 | P2 | 复判失败被转换为负例并覆盖原标签 | [src/linkrag_eval/golden_v2/qc.py:460](../../../src/linkrag_eval/golden_v2/qc.py) |
| D01 | P2 | 破同分收益的文字解释方向写反 | [docs/reports/llm_judge_pilot_2026_09_10.md:100](../../../docs/reports/llm_judge_pilot_2026_09_10.md) |
| D02 | P2 | 判断器参数文档仍描述旧版行为 | [scripts/README.md:23](../../../scripts/README.md) |
| D03 | P2 | L3 复现命令引用已迁移的旧评分目录 | [runs/post_recall/llm-judge-pilot-20260910/README.md:73](../../../runs/post_recall/llm-judge-pilot-20260910/README.md) |
| D04 | P3 | 历史 N09 的机制定论未标明后续解释已收窄 | [docs/reports/llm_judge_pilot_2026_09_10.md:117](../../../docs/reports/llm_judge_pilot_2026_09_10.md) |
| D05 | P3 | #23 复现入口仍称原候选快照未交付 | [docs/reports/list_collapse_2026_09_11.md:110](../../../docs/reports/list_collapse_2026_09_11.md) |
| D06 | P3 | 两处本地导航需要更正或注明缺件 | [docs/experiments/EXPERIMENT_LOG.md:127](../../../docs/experiments/EXPERIMENT_LOG.md) |

## 各项依据与建议

### C01 · P1 · 普通 run 会覆盖旧结果，同名基线变成自比

定位：[src/linkrag_eval/cli.py:803](../../../src/linkrag_eval/cli.py)。

**触发与影响：** 同一 run-label 和 top-k 重复执行（默认 run-top10），会复用同一 run_id。第828–837行先保存当前结果，随后才读取 --baseline；文件写盘和 SQLite 更新均允许覆盖。换 out-dir 也不能避免共享 SQLite 的同名覆盖。

**证据：** 两次 fake _do_run 的指标依次为1.0、0.0；第二次 --baseline run-top10 后仅剩一个结果文件，报告 current=0.0、baseline=0.0。证据 core-evidence.json / run_overwrite；SQLite覆盖另由 db_result_store.py:139–163 的 merge/delete 实现核对。

**建议方向，未实施：** 建议每次生成唯一运行ID，或在执行前明确拒绝既有ID；基线应在新结果写入前读取。

**历史实验影响：** 可能影响以前用普通 run 且重复标签保存的产物；本次未证明任何历史结果已遭覆盖。#18–#23 的独立运行目录不直接使用此保存入口。

### C02 · P1 · Alembic 环境变量入口绕过本地 SQLite 护栏

定位：[alembic/env.py:30](../../../alembic/env.py)。

**触发与影响：** 程序化 config.attributes URL 有SQLite校验，但 ALEMBIC_DATABASE_URL 原样返回，后续 engine_from_config/connect/run_migrations 会使用它。残留或误设该变量时，只要驱动和连接可用，普通迁移命令即可向其他数据库执行DDL。alembic.ini:3 还保留 MySQL DSN 的旧说明。

**证据：** AST提取实际 _resolve_url，传入 mysql+pymysql://example.invalid/tolink_rag_db 被接受。只验证URL解析，网络调用0；见 core-evidence.json / migration_guard。

**建议方向，未实施：** 建议对所有来源解析后的最终URL统一执行本地SQLite校验，并清除旧MySQL说明。

**历史实验影响：** 违反项目隔离约束，但未发现已经发生远端写入的证据。显式SQLite的T2迁移路径已有校验。

### C03 · P2 · SQLite BM25 的 coarse/fine 权重未应用到正文列

定位：[src/linkrag_eval/store/sqlite_bm25.py:264](../../../src/linkrag_eval/store/sqlite_bm25.py)。

**触发与影响：** FTS表的前五列是UNINDEXED元数据，coarse/fine在第六、七列。SELECT和ORDER BY只给 bm25 两个权重，实际文本列一直取默认1/1；配置默认2/1也未生效。

**证据：** 临时SQLite中，配置100/0和0/100所得两条分数都为1e-6。将参数置于第六、七列后，coarse命中为2.173913e-6、fine为0。见 core-evidence.json / bm25_weights。

**建议方向，未实施：** 建议两个表达式按全部列的位置传递权重，补一个能验证两字段权重改变排序的测试。修复后应作为新计算版本，不能覆盖既有候选。

**历史实验影响：** 这是实际配置与运行行为不符。凡使用该后端且两字段权重不同，声称的配置需要说明；仅凭此不能否定冻结候选上的排序比较，也不能认定必须重跑全部实验。

SQLite官方说明权重按表的全部列顺序对应，缺省列权重为1.0；与本次SQL复现一致。[SQLite FTS5 bm25文档](https://www.sqlite.org/fts5.html#the_bm25_function)。

### C04 · P2 · 普通 ingest 耗尽重试后仍以成功退出

定位：[src/linkrag_eval/app.py:97](../../../src/linkrag_eval/app.py)。

**触发与影响：** 批次最终失败只累计局部failed并跳过，run_ingest只返回成功数量；cli.py:707–708 无条件打印灌库完成并返回0。依赖退出码的流水线无法区别完整成功与部分或全部失败。

**证据：** 一个 passage 的fake索引器持续抛错、retries=1，函数正常返回0且未抛异常。见 core-evidence.json / ingest_failure。

**建议方向，未实施：** 建议汇总成功和失败数量并让CLI失败退出，或完成剩余批次后抛出明确的不完整状态。

**历史实验影响：** 影响普通旧入库入口。新的 exploration ingest 有独立失败状态；本次没有证明已完成的NevIR入库触发此缺陷。

### C05 · P2 · 候选缓存恢复会静默保留旧标签

定位：[src/linkrag_eval/retrieval/learning_to_rank/cache.py:78](../../../src/linkrag_eval/retrieval/learning_to_rank/cache.py)。

**触发与影响：** reusable只比较查询、用户、数据集、深度和alias；同ID样本更正 expected_chunk_ids/expected_doc_ids 后，旧缓存行仍原样输出。experiment.py:60开始直接由这些字段生成训练标签及分组。

**证据：** 首次标签old/[1]，再次同ID/query改为new/[2]，结果 resumed=1/fetched=0，输出仍old/[1]，下游标签仍old:1/new:0。见 experiment-reproductions.json。

**建议方向，未实施：** 建议复用routes时刷新当前监督及样本元数据，或明确拒绝不一致缓存；标签变化本身无需重新召回。

**历史实验影响：** 未证明历史实验曾触发。当前NevIR监督链与此旧 ltr cache 接口分开。

### C06 · P2 · MAP 的分母随实际返回长度缩小，漏召回也可得满分

定位：[src/linkrag_eval/metrics/retrieval.py:220](../../../src/linkrag_eval/metrics/retrieval.py)。

**触发与影响：** 指标名称是map、k=None，但AP除以 min(相关项数, 实际返回项数)。返回条数少于相关项数时，漏掉的相关项被移出分母，不同阈值或深度的结果不可作为普通AP/MAP直接比较。

**证据：** 参考有2个相关chunk，只返回其中1个且排第一，现实现返回1.0；普通AP应为0.5。见 experiment-reproductions.json。源码注释“避免虚高”与该边界行为相反。

**建议方向，未实施：** 建议普通AP按全部相关项归一化；如果要采用AP@K，应给出固定K、相应名称与截断规则，避免使用实际返回长度作隐式阈值。

**历史实验影响：** 历史报告出现MAP，但本次未重算逐题记录，不能断言具体成绩已错。当前NevIR指定段偏好主指标不使用该实现。

普通AP对所有相关项平均，未召回项贡献为0；上述0.5依据作者教材中的定义。[Introduction to Information Retrieval：ranked retrieval evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)。

### C07 · P2 · 参考无标题或图片时，产物新增元素被记为零误检

定位：[src/linkrag_eval/metrics/cleaning.py:230](../../../src/linkrag_eval/metrics/cleaning.py)。

**触发与影响：** heading_scores及image_scores（第307–308行）在参考元素为空时直接返回满recall、false_rate=0，没有检查产物是否凭空新增标题或图片。

**证据：** reference为Only text.，产物增加一个标题或图片，两者均返回false_rate=0；图片还返回recall=1、context_position_ok=1。见 experiment-reproductions.json。

**建议方向，未实施：** 建议区分双方均无元素与仅参考为空；产物非空时应计误检，其他无定义指标按明确约定处理。

**历史实验影响：** 属于清洗评价边界缺陷；没有证据表明当前NevIR主实验受影响。

### C08 · P2 · 改写缓存未校验模型和提示版本，却报告为当前模型

定位：[src/linkrag_eval/query_rewrite/planner.py:124](../../../src/linkrag_eval/query_rewrite/planner.py)。

**触发与影响：** resume只核对样本ID、原查询及非fallback；第161–162行报告当前planner身份。更换模型或提示版本后可复用旧计划并生成身份不一致的报告。

**证据：** old-model/old-prompt缓存配合new-model/new-prompt运行，fake调用0次，报告new-model，保存计划仍old-model。见 golden-rewrite-reproductions.json / cache。

**建议方向，未实施：** 建议恢复时校验模型及提示版本，不匹配则拒绝或明确重新生成；报告应反映实际产物身份。

**历史实验影响：** 属于保留的Query改写工具。未发现它影响当前固定候选主实验数字。

### C09 · P2 · 复判失败被转换为负例并覆盖原标签

定位：[src/linkrag_eval/golden_v2/qc.py:460](../../../src/linkrag_eval/golden_v2/qc.py)。

**触发与影响：** 模型未返回有效字典时 _review_one 转成False/0；缺候选正文（第261–268行）也如此。默认review_overrides将它当有效复判结果写回。真实generate_json的超时或HTTP失败可以返回None。

**证据：** fake复判返回None，经label_review_queue和adjudicate_judgments，原True/grade2变False/grade0，adjudication_status=review_changed。见 golden-rewrite-reproductions.json / review。

**建议方向，未实施：** 建议保留复判失败或缺正文的未完成状态，不覆盖原判断；失败也不应计成已完成复判。

**历史实验影响：** 属于历史Golden V2质检入口，未证明当前研究标签或主实验受影响。

### D01 · P2 · 破同分收益的文字解释方向写反

定位：[docs/reports/llm_judge_pilot_2026_09_10.md:100](../../../docs/reports/llm_judge_pilot_2026_09_10.md)。

**触发与影响：** 正文写E0破同分比融合分多纠正16题、少改坏17题。实际同段及 judge-statistics-20260911/tables.md:6,8 分别为融合132/29、E0 116/12（纠正/改坏）。

**证据：** 116−132=−16、12−29=−17，净正确数只多1；现文把“少纠正”写成“多纠正”，将取舍说成两方面都更好。聚合数据本身一致。

**建议方向，未实施：** 建议仅纠正文案为少纠正16、少改坏17、净多正确1；不改原表。

**历史实验影响：** 影响报告解释与论文引用，不改变现有计算结果。

### D02 · P2 · 判断器参数文档仍描述旧版行为

定位：[scripts/README.md:23](../../../scripts/README.md)。

**触发与影响：** 称--num-ctx控制OpenAI输出token上限、本地effort固定none；当前脚本由独立--max-tokens控制输出预算，--num-ctx用于校验服务上下文，--think开启思考并将effort记录为think。

**证据：** 对照 scripts/llm_judge_pilot.py:157–160、422–427；当前冻结Qwen配置也明确think=true、max_tokens=6144。

**建议方向，未实施：** 建议同步参数说明，正式复现指向已有冻结配置，避免按旧说明重新猜参数。

**历史实验影响：** 现有正式运行按冻结配置执行，未发现运行参数错误；影响后续照抄文档复现。

### D03 · P2 · L3 复现命令引用已迁移的旧评分目录

定位：[runs/post_recall/llm-judge-pilot-20260910/README.md:73](../../../runs/post_recall/llm-judge-pilot-20260910/README.md)。

**触发与影响：** train-l3命令使用l3s-train-judge/scores.jsonl；同README第14行已明确正式完整评分在l3s-train-judge-8w，前身目录移至_superseded。

**证据：** 仅检查存在性：原项目目录旧路径不存在，l3s-train-judge-8w/scores.jsonl存在。未读取这些评分内容。

**建议方向，未实施：** 建议命令引用正式8w评分路径；复现输出目录另按现有拒绝覆盖规则选择。

**历史实验影响：** 阻碍现有产物上的L3复现，未影响已完成训练的原成绩。

### D04 · P3 · 历史 N09 的机制定论未标明后续解释已收窄

定位：[docs/reports/llm_judge_pilot_2026_09_10.md:117](../../../docs/reports/llm_judge_pilot_2026_09_10.md)。

**触发与影响：** 第9、117、152行仍使用已定位到38维输入、证明了机制、缺少的正是某类信号等表述；研究计划第449行已明确N08只证明新增提取路径缺口，不能直接解释E0全部错排。报告有明确历史日期，应保留当时事实，避免把历史推断当当前定论。

**证据：** N09主报告与 docs/plans/post-recall-research-plan.md:449 的解释范围不一致；新报告已披露限制，因此这里按历史说明同步项处理。

**建议方向，未实施：** 建议在旧推断旁添加后续解释收窄的说明与链接，不重写历史数字，不要求追加实验。

**历史实验影响：** 论文引用时需采用当前限定解释；本项不是新的计算错误或现有主结论失效。

### D05 · P3 · #23 复现入口仍称原候选快照未交付

定位：[docs/reports/list_collapse_2026_09_11.md:110](../../../docs/reports/list_collapse_2026_09_11.md)。

**触发与影响：** 产物入口仍写原候选snapshot未交付，但同报告第15–19行已记录补交及#19验收；目前仍缺的是成员逐题模型分数。

**证据：** 同一报告内部的交付范围自相矛盾。候选输入在原工作区存在的状态由本次文件存在性检查支持，不重读Test。

**建议方向，未实施：** 建议同步该入口的缺失范围，保留首批交付当时的历史事实。

**历史实验影响：** 不会改变成绩，但会误导成员判断是否还需索取候选或重新采集。

### D06 · P3 · 两处本地导航需要更正或注明缺件

定位：[docs/experiments/EXPERIMENT_LOG.md:127](../../../docs/experiments/EXPERIMENT_LOG.md)。

**触发与影响：** T05链接指向runs/post_recall/README.md#其他历史目录，当前无此标题；paraphrase-probe-20260912/ai-review/report.md:15 的review.jsonl在两个本机工作区及现有Git worktree中均未找到。

**证据：** 93份项目Markdown的链接检查经人工排除带:行号的应用链接后，确认1个失效锚点和1个当前本地缺件链接。review.jsonl只属准备阶段AI逐条意见，不是36项正式人工审核文件。

**建议方向，未实施：** 建议锚点指向现有段落；AI逐条意见如在其他归档则补有效位置，否则如实注明本地未取得，不补造记录。

**历史实验影响：** 导航问题，不据此声称原件永久丢失；正式#22人工审核、评分与结果不受此缺件影响。

## 建议处理顺序与未覆盖边界

1. 先由负责人决定C01/C02（历史结果保存和SQLite隔离）、D01（确定文字算术错误）。
2. 完成#26复现包前，处理D02/D03及实际准备使用的缓存／失败入口。C03若修复，明确旧实验实际权重和新计算版本，不能把修复后的召回覆盖原候选。
3. 历史Golden／改写／清洗工具可按后续是否继续使用排序；D04–D06属于说明与导航整理。

没有读取官方Test逐题、运行新模型、训练、重新召回或连接活栈；没有核对全部被忽略数据库正文和历史逐题产物，也没有逐条验证所有文献与外部日期。现行运行核心、主要实验流程和文档入口做了人工审查；全部跟踪Python代码有语法／静态检查，但不声称对每个历史脚本逐行证明正确。

已排除的误报：golden_v2/labeling.py循环闭包在每轮await gather结束后才更新query/semaphore，不是并发Bug；两条带“:行号”的本地应用链接实际文件存在；本地忽略产物不随新worktree出现不代表删除。#16重试／配置偏差、#23首次交付与来源依赖限制、论文工作稿尚未写完均有既有明确记录，本次没有冒充新发现。

原审查收尾时，所有发现均为 `recorded_not_implemented`；当时没有实施修复，也没有替负责人创建新的整改 issue。后续处理见下方追加记录。


<a id="followup-20260914"></a>
## 2026-09-14 后续核查与文档修订

核查基于 `d59cbca`（已含 #48／#49／#50），只读原聚合、当前源码和路径，并用临时合成环境复现 C01／C02。核查阶段先修正文档、仅记录 C01／C02；随后按负责人要求创建[总 issue #54](https://github.com/ql-link/LinkRag-Eval/issues/54)，并完成 B3／C02、B4／C01 的实现与验收，与 B1／B2、D02–D06 的文档修正统一交付 [PR #55](https://github.com/ql-link/LinkRag-Eval/pull/55)。合并状态以 PR 页面为准。原 `findings.json`、复现脚本及 `evidence/` 保留审查时的字节与身份，下表是追加的当前状态。

| 原项／关联项 | 本次结论与处理 | 证据及边界 |
| --- | --- | --- |
| D01（截图 B1） | 已纠正为 E0 破同分少纠正 16、少改坏 17，净多正确 1。 | 保存的 K20 确认聚合为融合 132／29、E0 116／12；只修文字，原表与结果不改。 |
| 指标术语（截图 B2） | 试点、Test、列表报告与运行入口统一使用“单查询严格偏好准确率”；完整配对的“双向全对率”另列。 | [研究计划统一定义](../../plans/post-recall-research-plan.md#metric-terminology)对齐 `strict_correct / 查询数` 与 `both_directions_correct / 完整配对数`，计算和数字不变。 |
| D02 | 主脚本文档已随 #48 更新；本次补齐 CLI 帮助里 `--think` 时默认输出预算的 4096 下限。 | 实际预算函数未改，只修 `--max-tokens` 帮助文字；正式复现仍依各自保存配置。 |
| D03 | 已改为正式 `l3s-train-judge-8w/scores.jsonl`，示例输出与新模型引用使用独立复跑目录。 | 旧路径不存在、正式路径存在；只核对存在性和命令语法，没有执行训练或评分。 |
| D04 | 在 N09 的输入定位、背景约束、L3 与总结段旁补充解释范围和后续入口。 | 新信号可被利用的证据不等于已隔离全部错排成因；保留原观察、数字及当时推断身份。 |
| D05 | 同步报告和运行入口：#19 快照已补交验收，#49 N=8 本地重放已完成。 | 原成员逐题分数／执行日志仍未取得；原件与本地重放分开，不追认原冻结时间线。 |
| D06 | T05 改到现有产物导航锚点；AI 预审报告及运行 README 同步说明逐条 JSONL 当前未取得。 | 已有报告与正式人工审核不是该缺件；不补造记录，也不据本地未找到断言永久丢失。 |
| C03 | 已由 [#50／PR #53](https://github.com/ql-link/LinkRag-Eval/pull/53)修复并合入 master。 | 历史快照仍解释为正文权重 1／1，修复后新召回须使用新快照，详见[架构](../../architecture/decoupling-plan.md#独立存储)。 |
| C02（截图 B3） | 已统一本地 SQLite 校验，删除配置异常吞掉后的回退和旧 MySQL 说明／转换。 | 程序化 URL、环境变量、eval 配置按优先级选择，在线／离线均在连接或迁移前校验；未对真实远端执行操作。 |
| C01（截图 B4） | 已在普通 run 召回前拒绝文件／SQLite 冲突，基线提前读取，同名或缺失明确报错。 | 文件锁与 SQLite 主键占位防止并发覆盖；失败保留台账和碎片，其他消费者幂等接口不变。没有改写历史结果。 |
| Ruff（截图 B5） | 未执行批量修复，不将告警逐条直接认定为功能缺陷。 | 当前检查数与历史范围的差别见下文。 |

C02 的修复前核验提取 `_resolve_url`，环境变量中的 MySQL URL 被接受，而程序化同类 URL 被拒绝。只执行 URL 解析，未加载数据库驱动或连接数据库。修复和对应入口见 [alembic/env.py](../../../alembic/env.py)。

C01 的修复前临时 fake 复现先保存 1.0，再以同名 run 和 baseline 保存 0.0，最终只剩一个结果文件，比较为 `current=0.0 / baseline=0.0`。数据库保存、召回均用 fake，并禁止 socket 连接；临时目录在核验后自动清除，没有覆盖原审查证据。修复使用临时 SQLite 与 fake 召回验证：重复 ID 在召回前拒绝，跨目录共享库亦然；新标签读取旧基线时比较为 `current=0.0 / baseline=1.0`。定位为 [cli.py](../../../src/linkrag_eval/cli.py) 的 `_do_run` 及文件／SQLite 保存入口。现行 NevIR 采集显式传入 SQLite URL，#18–#23 与 #49 的独立评分目录不走普通 `_do_run` 保存入口；这只限定已核查链路，不证明其他历史入口没有风险。

实现新增 66 项合成测试：迁移 URL 41 项、普通 run 历史保全 25 项。首批测试在旧实现上分别为 20 failed／21 passed、11 failed／1 passed，修复后全部通过；普通 run 另覆盖了并发、取消、残留产物及数据库孤立指标。完整非 integration 回归 1,469 passed／23 skipped／3 deselected（6 个依赖既有 warnings），CI 单独收集的脚本测试 60 passed。新增代码无 Ruff 告警；受影响的三个旧模块共 8 条既存告警与修改前规则／消息一致，没有借本 issue 批量修复。使用说明见[独立存储](../../architecture/decoupling-plan.md#独立存储)。

Ruff 0.16.2 对 344 个跟踪 Python 文件检查（排除 `.ai`／vendor）得到 222 条；其中新归档的三个 `docs/audits/master-20260913/reproduce/` 脚本贡献 6 条。排除该历史脚本目录后为 216 条，各规则数量与原 216 条一致。主要涉及导入排序、语法更新、可执行标志与异常规范，也包含 B023、B008、ASYNC230 等可能涉及行为的提示，不能概括为“全部只有风格问题”。本次不改代码格式或原归档脚本。

D02–D06 中包含 NevIR 的实际复现入口、机制解释和交付导航，不能整体归为与主线无关。C04–C09 的实现仍保持原审查记录，本轮没有扩展复现或修复。没有重跑模型、召回、训练或来源组统计，没有更改实验数字，也没有读取或修改论文稿件。
