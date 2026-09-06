# Robust Fusion 历史导航

本索引说明原 Robust Fusion 研究流程的历史身份。下列旧协议退出活动执行身份，仍保留在 `docs/plans/` 原路径，正文与字节保持不变，便于核对报告、锁与原文哈希。这里没有移动原稿，也没有把未完成流程标成完成。

当前研究与项目进度见 [CURRENT_STATUS](../../CURRENT_STATUS.md)，方法讨论见[独立审查与回应](../../plans/research-direction-review-2026-09-06.md)。本次实际变更、Git 版本和验证见[重构执行记录](../../plans/research-restructure-execution-2026-09-06.md)。

## 原协议清单

| 原文件 | 历史用途 |
| --- | --- |
| [robust-fusion-research.md](../../plans/robust-fusion-research.md) | 原科研协议与 Gate 逻辑 |
| [robust-fusion-engineering.md](../../plans/robust-fusion-engineering.md) | 原工程实施协议与契约封存步骤 |
| [robust-fusion-todo.md](../../plans/robust-fusion-todo.md) | 原任务顺序，不再是当前任务入口 |
| [robust-fusion-reviewer-clarifications.md](../../plans/robust-fusion-reviewer-clarifications.md) | 原审稿澄清 |
| [robust-fusion-publication.md](../../plans/robust-fusion-publication.md) | 原发表路径与治理要求 |
| [robust-fusion-similarity-manifest.md](../../plans/robust-fusion-similarity-manifest.md) | 原相似度测量与资格协议 |
| [robust-fusion-internal-stress-v6.md](../../plans/robust-fusion-internal-stress-v6.md) | Internal 数据构建与流程 |
| [robust-fusion-c2-boundary-supplement.md](../../plans/robust-fusion-c2-boundary-supplement.md) | 原 C2 边界补充方案 |
| [robust-fusion-annotation-handbook.md](../../plans/robust-fusion-annotation-handbook.md) | 原标注规范 |
| [robust-fusion-annotation-full-guide.md](../../plans/robust-fusion-annotation-full-guide.md) | 原标注操作步骤 |
| [robust-fusion-human-task-entrypoints.md](../../plans/robust-fusion-human-task-entrypoints.md) | 原人工任务映射与入口约束 |
| [robust-fusion-r1-to-r2-inheritance-matrix.md](../../plans/robust-fusion-r1-to-r2-inheritance-matrix.md) | R1 到 R2 的继承关系 |
| [robust-fusion-r2-research.md](../../plans/robust-fusion-r2-research.md) | 原 R2 研究协议 |
| [robust-fusion-r2-similarity-measurement.md](../../plans/robust-fusion-r2-similarity-measurement.md) | 原 R2 相似度测量 |
| [robust-fusion-r2-automatic-execution-v1.md](../../plans/robust-fusion-r2-automatic-execution-v1.md) | 原自动执行规则，不再据此执行 |
| [robust-fusion-r2-gate-a-delta-checklist.md](../../plans/robust-fusion-r2-gate-a-delta-checklist.md) | 原 Gate A 差异清单 |
| [robust-fusion-r2-human-review-finalization-v1.md](../../plans/robust-fusion-r2-human-review-finalization-v1.md) | 原仲裁与 finalizer 规范，不表示已经完成 |
| [robust-fusion-r2-source-authorship-v7-codex.md](../../plans/robust-fusion-r2-source-authorship-v7-codex.md) | 原 source authorship 记录 |
| [robust-fusion-r2-source-lock-v7-1.md](../../plans/robust-fusion-r2-source-lock-v7-1.md) | 原 source lock 记录 |
| [研究审稿意见.md](../../plans/研究审稿意见.md) | 历史独立审查材料 |
| [面向检索增强生成的多路检索融合查询级退化风险评估与策略选择.md](../../plans/面向检索增强生成的多路检索融合查询级退化风险评估与策略选择.md) | 历史研究方案原稿 |

“冻结”“唯一下一步”“自动执行”等旧正文措辞只描述当时协议，不恢复当前执行身份，也不为新的实验提供授权。当前候选方法仍未定案，旧 Gate／相似度门槛不自动成为新研究的前置条件。

## 保留的文献、任务与证据

- [文献综述](../../plans/robust-fusion-literature.md)与[证据卡片](../../plans/robust-fusion-evidence.md)保留来源；文献内容不能表述为项目已做过的实验。
- [旧人工 registry](../../plans/robust-fusion-human-task-registry.json)与[旧仲裁 HTML](../../plans/robust-fusion-r2-adjudicator-beginner-guide.html)保留原样。对应 symlink、人工提交和锁继续保留，但不作为活动任务。当前没有人工任务；空 registry 和专用 checker 已在[后续简化](../../plans/runtime-simplification-2026-09-06.md)中移除。
- 历史报告和运行证据通过[报告索引](../../reports/REPORT_INDEX.md)查找。R1 历史结果仍为 `INCONCLUSIVE`；R2 最后记录状态仍为待仲裁。流程退役不表示标注完成、效度成立或结论翻转。
- 已有 Qwen 负收益与其他历史负结果保留在[LambdaMART 实验记录](../../experiments/ltr-fusion-v1.md)及原报告中，不能因为新方向调整而删除或重写。

## 恢复与核对

源码保全标签：`research-pre-restructure-20260906`，对应提交 `4d31f18`。可用 `git show research-pre-restructure-20260906:相对路径` 读取重构前文件，或在独立目录检出标签核对，避免覆盖当前工作区。旧协议在当前分支也保留原路径，不需要为阅读而恢复旧代码。

Git 忽略的 runs、derived、人工产物等使用独立备份与 manifest 核对，不能仅靠 Git 标签恢复。备份位置、覆盖范围与实际删除记录见[重构执行记录](../../plans/research-restructure-execution-2026-09-06.md)。本索引没有授权运行旧流程、重开封存结果或清除未列入删除范围的文件。
