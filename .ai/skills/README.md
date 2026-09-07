# 保留技能选读

本目录继承上游共享技能，只按具体任务选读，不作为 LinkRag-Eval 的默认执行流程。当前规范以[AGENTS](../../AGENTS.md)为准；命令查[脚本目录](../../scripts/README.md)，研究材料查[文档选读](../../docs/DOCUMENT_CATALOG.md)。

原目录声称的专用技能检查脚本、pre-commit 集成及固定交付链不适用于当前仓库。旧技能中的分支、路径、活栈测试、提交或外部操作要求，须以当前规范、实际代码和用户授权核对；不能因选读技能就自动执行。

| 需要参考什么 | 技能 | 使用范围 |
| --- | --- | --- |
| 需求与实现组织 | [flow-router](flow-router/SKILL.md)、[brief-generator](brief-generator/SKILL.md)、[acceptance-generator](acceptance-generator/SKILL.md)、[technical-design](technical-design/SKILL.md)、[implementation-execution](implementation-execution/SKILL.md) | 按任务需要参考，不预设逐阶段文档或前置审批 |
| 测试与审查 | [auto-test](auto-test/SKILL.md)、[run-all-tests](run-all-tests/SKILL.md)、[code-review-and-quality](code-review-and-quality/SKILL.md)、[feature-completion-audit](feature-completion-audit/SKILL.md)、[contract-guard](contract-guard/SKILL.md) | 实际测试命令与集成范围依当前仓库；不默认调用远端 |
| 文档与注释 | [config-contract-sync](config-contract-sync/SKILL.md)、[doc-maintenance-sync](doc-maintenance-sync/SKILL.md)、[agents-tree-sync](agents-tree-sync/SKILL.md)、[code-annotator](code-annotator/SKILL.md)、[blog-writer](blog-writer/SKILL.md) | 更新对应主文档；不复制旧目录结构或新建无用途的材料 |
| 分支与外部协作 | [branch-pr-workflow](branch-pr-workflow/SKILL.md)、[cowork-issue-sync](cowork-issue-sync/SKILL.md) | 分支以 AGENTS 和用户要求为准；提交、发布、外部通信须有相应授权 |
| 故障定位 | [incident-triage](incident-triage/SKILL.md) | 按当前组件与实际日志定位，不恢复旧生产链路 |
| 数据库迁移 | [alembic-migration](alembic-migration/SKILL.md) | 本项目使用根目录 Alembic 与本地 SQLite，生产迁移保持隔离 |
| 上游生产专项资料 | [mysql-ddl-conventions](mysql-ddl-conventions/SKILL.md)、[mq-middleware](mq-middleware/SKILL.md)、[swagger-annotation](swagger-annotation/SKILL.md) | MySQL、MQ、FastAPI 的旧上游资料，不作为评测项目默认要求 |
| 技能编写 | [skill-creator](skill-creator/SKILL.md)、[component-skill-author](component-skill-author/SKILL.md) | 仅在确有技能创建或维护任务时使用 |

原治理说明见[修改前 Git 版本](https://github.com/ql-link/LinkRag-Eval/blob/af6267d69cb9a4aeb194bf6c49eb589df8912bac/.ai/skills/README.md)。各技能原文保留，本页不新增检查工具或基础设施。
