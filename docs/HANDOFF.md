# LinkRag-Eval 交接说明

> 文档职责：帮助下一轮工作识别当前入口、工程边界和历史材料。项目进度、检查结果和下一步只维护在 [CURRENT_STATUS.md](CURRENT_STATUS.md)，本文件不另列容易过期的任务序列。

## 继续工作前

先查看当前状态、`git status --short` 和[重构执行记录](plans/research-restructure-execution-2026-09-06.md)，再确定当前任务范围。重构已由用户授权，按分段提交记录实际变更；不要把原盘点清单当成已经执行的删除结果。

本仓库只写本地评测 SQLite 和含 `eval` 前缀的 Qdrant collection。生产依赖只能经允许的 adapter 复用纯计算、被测对象与 Qdrant 原语，具体边界见 [AGENTS.md](../AGENTS.md) 和[解耦架构](architecture/decoupling-plan.md)。密钥、本地数据库与原始数据不进入版本库。

## 保留的工程基线

- 独立入库、Dense／Learned Sparse／SQLite FTS5 BM25 召回、候选证据、指标与报告能力。
- 现有 `candidate_difference_v3` 的 38 维 LambdaMART、冻结模型、在线契约、Shadow 与回退能力；保留实现不等于批准生产全量切换。
- 核心单元与生产依赖契约测试、Qdrant 前缀护栏、eval 自持配置和存储隔离。
- 历史数据、报告、人工提交、锁、模型与单次运行证据；清理旧流程不改变它们的来源和使用限制。

工程细节与结果见[LambdaMART 实验记录](experiments/ltr-fusion-v1.md)和[报告索引](reports/REPORT_INDEX.md)。Qwen 直接重排及接入分数特征的历史负结果应继续保留，具体结论限定在当时的配置与数据；不能据此宣称所有文本方法无效，也不能抹掉已观察到的负收益。

## 当前研究边界

研究问题仍围绕三路召回后的固定候选集合：如何利用候选的可见关键差异及逐路分数／排名改进融合或重排。不回原文补信息，不改召回。研究方法保持暂定；差异引导的局部覆盖、词序／邻近特征、候选比较或局部交换等讨论均不是冻结的实现要求。

[独立审查与回应](plans/research-direction-review-2026-09-06.md)保留讨论依据和未决事项；[关系融合概念稿](plans/post-recall-relational-fusion-concept-2026-09-05.md)仅作早期候选方案记录。任何具体步骤、参数、方法版本或评测设计，都不能仅因写在这些稿件中而获得执行授权。

## 旧协议与人工任务

原 Robust Fusion、R1／R2、Gate、Internal、相似度及人工仲裁协议退出活动执行身份，正文仍保留原路径与字节。统一从[历史导航](archive/robust-fusion/README.md)进入，不继续执行其“唯一下一步”、自动执行、finalizer 或旧任务清单。R1 历史结论仍为 `INCONCLUSIVE`，R2 的最后记录状态仍是待仲裁；退役不等于补完验证。

当前人工任务由 [human_tasks/registry.json](../human_tasks/registry.json)登记，默认活动列表为空。入口校验为 `python3 scripts/check_human_task_entrypoints.py`；它只检查登记内容，不仲裁答案或执行研究阶段。旧 registry、HTML、symlink 与提交保留作历史，不通过旧入口继续催办任务。

已封存的 Blind 及被限定用途的数据继续遵守其曝光和使用边界；本次整理不得读取封存结果来选方法、调参或形成新结论。历史汇总报告可供理解已有证据，不能当作新研究的独立验证集。

## 版本恢复与文档维护

重构前源码基线是 `4d31f18`，标签 `research-pre-restructure-20260906`。通过 `git show research-pre-restructure-20260906:相对路径` 查看旧文件，或在独立目录检出标签做恢复核对；不要直接覆盖正在工作的分支。Git 忽略的证据另有 tar 与 manifest，保全范围和位置见[执行记录](plans/research-restructure-execution-2026-09-06.md)。未复制入备份的数据库、公共下载与模型缓存仍保留原处，不能因 Git 不跟踪而删除。

新报告使用新的 run／batch 目录或时间戳文件名，保留旧报告原路径。生成报告后运行 `python3 scripts/build_report_index.py` 更新索引，交付前执行其 `--check`。文档导航和使用身份维护在[文档目录](DOCUMENT_CATALOG.md)；不要修改历史协议来伪装成已经完成的新方案。
