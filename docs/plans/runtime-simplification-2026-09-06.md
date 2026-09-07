# 当前运行链路简化

用户要求：当前版本不保留没有必要的旧兼容，不把哈希／SHA256 当作科研流程的默认前置。具体研究方法继续暂定。

## 文件处理

上轮 96 个 tracked 旧源码／脚本／测试已经实际删除，本轮不恢复它们。残留字节码及本轮无实际用途的工具移入废纸篓，原报告、模型、人工提交和旧清理记录保留作历史。

废纸篓位置：`/Users/kawauso/.Trash/LinkRag-Eval-cleanup-20260906-133055`。Git 保存源码修改；本轮不生成逐文件哈希台账。

本批移入废纸篓的源码／配置／测试：

- `src/linkrag_eval/compute/similarity.py`
- `src/linkrag_eval/compute/vector_diagnostics.py`
- `src/linkrag_eval/retrieval/candidate_evidence.py`
- `src/linkrag_eval/human_task_entrypoints.py`
- `scripts/check_human_task_entrypoints.py`
- `tests/unit/test_similarity.py`
- `tests/unit/test_vector_diagnostics.py`
- `tests/unit/test_candidate_evidence.py`
- `tests/unit/test_human_task_entrypoints.py`
- `human_tasks/registry.json`
- `src/linkrag_eval/store/database_migration.py`
- `scripts/migrate_eval_mysql_to_sqlite.py`
- `tests/unit/test_database_migration.py`
- `scripts/render_bm25_sqlite_ab_acceptance.py`
- `tests/unit/test_bm25_sqlite_ab_acceptance.py`

同时清理旧 `robust_fusion/` 字节码目录、旧脚本／测试对应字节码和上述工具对应字节码。未清理其他模块缓存。

## 简化依据

- 四个新抽离模块及 checker 没有现有业务消费者，仅有对应单测；暂不为可能的未来需求保留框架。
- 当前无人工作业，删除空注册表和专门的校验流程；历史指南与人工数据仍可追溯。
- MySQL 迁移已结束，删除一次性迁移源码、脚本和测试；评测继续使用本地 SQLite。
- 旧 BM25 专用验收脚本依赖内容哈希门槛，已非当前任务；历史结果报告保留。


下列三个仅生成旧 v1／v2 报告、没有当前调用方的脚本也已移入同一废纸篓位置；通用报告工具和原结果报告保留：

- `scripts/build_ltr_candidate_feature_report.py`
- `scripts/render_scale20k_report.py`
- `scripts/render_ltr_2000_evaluation_report.py`

最后移除旧 Blind v4 的专用 freeze／claim／seal 执行器、CLI 三个子命令及对应测试。这是旧版本的一次性验收流程，不是当前模型包校验；历史 Blind 数据、结果和使用边界保留，新研究不继承其配置哈希与固定样本门槛。以下两文件及字节码移入同一废纸篓位置：

- `src/linkrag_eval/golden_v2/blind_v4.py`
- `tests/unit/test_blind_v4_gate.py`

## 当前运行行为

- 配置与工厂只接受已有实际实现：OpenAI Dense／Alt、Ark Sparse、本地 FTS5 或不装配第三路的 stub；旧提供方别名和废弃模式不再回退。
- Snapshot 使用逐路阈值，取消旧单一阈值字段。历史结果保留可查看，新版加载器不保证重放旧格式；没有为旧快照新增兼容转换。
- 每次评测只记录 Git 提交及是否存在未提交修改，不读取未提交文件正文计算摘要。
- BM25 记录路径、schema、数量和参数，不遍历 token 正文生成全库摘要；数量相同不被表述为内容相同。
- 候选缓存只有查询、用户、数据集、逐路深度和实际 Alias 配置匹配时才复用；旧缓存缺少必需字段就重新生成，使用直接比较，不增加摘要。
- 新冻结模型不再对训练缓存整文件计算 `training_data_sha256`，也不把整个 manifest 打印到终端。当前模型包格式仍包含该字段以保持现有 v3 包与生产加载接口一致，新导出写空值；不改写已冻结模型包，不把该字段当成校验要求。

## 必要保留

| 用途 | 为什么保留 |
| --- | --- |
| 当前模型／回退文件完整性与特征顺序契约 | 防止加载损坏或与当前 38 维特征不一致的模型；有实际加载器和契约测试消费。 |
| 正文变化检测、去重与缓存失效 | 避免沿用错误缓存或重复昂贵编码；不是科研准入步骤。 |
| 确定性抽样、数据分组与 collection 路由 | 同一输入产生相同分组或存储位置；不改变已有基线实验划分与存储寻址。 |
| 依赖固定版本及包管理器锁文件 | 对齐当前被测生产接口和安装内容，由现有工具自动维护。 |
| 明确导入包的完整性检查 | 防止传入不完整／错配的数据包；不要求所有科研步骤重复封存。 |

未把哈希算法本身当成问题，也不把它当成实验有效性的证据。未来增加校验或兼容必须先说明当前用途，不能以“可能复用”或“沿袭旧协议”为由保留。

## 验证结果

- 单元、生产契约与依赖边界测试合计 **359 passed**；未调用真实编码、召回或数据库服务。
- CLI 主入口、`golden-v2`、`ltr` 帮助正常，旧 Blind 三个命令已不再注册；报告索引检查通过。
- 锁文件离线一致性检查、`git diff --check` 通过。38 个修改的 Python 文件相对改前版本没有新增 Ruff 问题；仍有 19 条既存问题，因此不表述为全仓静态检查零告警。
- 20 个受 Git 跟踪的移出文件逐项确认位于上述废纸篓目录；旧 `robust_fusion` 字节码目录已离开仓库。当前冻结模型目录没有修改。

当前版本有意停止支持已移除的旧配置、旧快照字段和专用命令；历史文件保留不等于新版可以直接重放。具体研究方法继续暂定，本次没有新增排序算法、训练或正式实验。


<a id="recovery"></a>

## 版本与备份恢复

- 本地重构前源码：标签 `research-pre-restructure-20260906`，提交 `4d31f18`；在独立目录查看或恢复，避免覆盖正在工作的分支。首次移除旧执行链路的提交为 `0db80e8`，后续运行链路简化为 `b92e460`；远端工程基线已由 [PR #5](https://github.com/ql-link/LinkRag-Eval/pull/5) 收录。
- 既有独立备份：`/Users/kawauso/Documents/Projects/LinkRag-Eval-restructure-backups/20260906-122751/`。`source-before-restructure.bundle` 保存当时的源码与本地标签；`protected-research-artifacts.tar` 保存研究运行、derived、Internal Dev、人工作业链接及当时纳入的论文副本；原 `manifest.json` 记录范围。需要完整恢复时使用该备份，不在本轮重新生成清单。
- 原备份未纳入根级工作数据库、公共下载、下载模型缓存及密钥；旧 Internal v6 的四个 SQLite 文件随其运行目录归档，不代表备份了全部数据库。后续文件保留与清理、当前英文实验未覆盖的范围见[存放总览](../WORKSPACE_MAP.md)，不能仅靠 Git 或上述 tar 恢复全部本地环境。
- 本次移除的 21 份旧计划、清理台账和重复入口，可以从[文档清理前的 Git 版本](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/)查看，或用 `git show 50f3a9b0ead581fb17fc3e4080c70361c9f24475:相对路径` 在本地读取。原协议与旧执行记录不要求继续占据当前工作树。
