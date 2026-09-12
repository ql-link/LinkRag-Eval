# 文档选读

按当前要回答的问题选一份文档，不必从头读完整个目录。这里维护阅读入口与用途；进度、设计和实证分别在其主文档中维护。

## 先按问题选择

| 你要确定什么 | 首选文档 | 阅读范围与身份 |
| --- | --- | --- |
| 现在做到哪一步，接下来做什么？ | [当前状态](CURRENT_STATUS.md) | 先读顶部当前方向；下方“上一阶段”只记录历史进度 |
| 做过哪些实验，包括失败和中止？以后怎样记录？ | [逐次实验台账](experiments/EXPERIMENT_LOG.md) | 逐项范围、结果身份与原记录；包含长报告里的多轮实验及补登缺口 |
| 各类文件存在哪，Git 和备份覆盖什么？ | [存放总览](WORKSPACE_MAP.md) | 包括本地忽略产物、当前英文实验的保存链及历史清理判断 |
| 当前研究问题、边界与对照思路是什么？ | [研究计划](plans/post-recall-research-plan.md) | 先看 §1.3 的固定开源主方案、§6 的对照与 §8 的顺序；§2 为历史设计，不是待办清单 |
| 多人并行阶段谁做什么、改哪些文件、依赖顺序？ | [并行研究计划](plans/parallel-research-plan-2026-09-10.md) | 任务对应 GitHub issue #14–#27；只维护分工与规则，结果看报告 |
| 哪次实验能回答我的效果或诊断问题？ | [报告选读](reports/REPORT_INDEX.md) | 按问题选实证，并核对开发／确认／机械诊断口径 |
| 成对指标与全池列表为何不一致，背景弱负例有何结果？ | [列表诊断与 N=8 报告](reports/list_collapse_2026_09_11.md) | 开发／确认本地复验与成员 Test 聚合分列，保留成对精度损失 |
| 正式英文 Test 最终结果、BGE 对照和中断成本是什么？ | [官方 Test 报告](reports/nevir_official_test_2026_09_12.md) | 固定 K20 主方案、主／敏感性口径、来源组区间及 #40 恢复记录 |
| 开源判断器为什么选 14B，候选比较是否齐全？ | [开发选模报告](reports/open_judge_selection_2026_09_11.md) | 8B、14B 与 BGE 的统一比较，区分原选择依据与后补结果 |
| 数据在哪，哪些已用于训练或开发？ | [数据入口](../data/README.md) | 实际输入、划分与使用范围，不从文件名猜用途 |
| 中文／英文基线用哪个目录、配什么规则？ | [模型入口](../models/README.md) | 当前两个模型的路径、契约与旧名称对应 |
| 要调用什么脚本，依赖哪些已有产物？ | [脚本与命令入口](../scripts/README.md) | 入口、输入输出、训练／远端／本地动作；历史脚本另列 |
| 某次运行的配置、模型、统计和日志在哪？ | [实验目录](../runs/post_recall/README.md) | 先读对应实验的短 README，再查具体产物 |
| 修改代码要遵守什么，模块职责在哪？ | [实现约定](../AGENTS.md) → [解耦架构](architecture/decoupling-plan.md) | 当前工程规范及依赖边界，不用历史实验报告推定架构 |
| 为什么保留或放弃某个研究想法？ | [独立审查与回应](plans/research-direction-review-2026-09-06.md) | 附录 H 为当前 Qwen 角色和主线纠偏；§3、附录 F/G 保留历史依据，讨论不等于实验结果 |
| 某个文献判断的原始依据在哪？ | [文献地图](plans/robust-fusion-literature.md) | 定位论文与证据范围；本地全文位置见[论文目录](papers/README.md) |

资料缺失时，区分“没有这份证据”和“本地缺少产物”。Git 忽略的数据与模型不一定随 clone 出现；位置与恢复方式按对应入口查询。

## 追溯旧工作时再读

| 要追溯什么 | 入口 | 使用身份 |
| --- | --- | --- |
| Qwen 失败、早期融合与 LTR 演进 | [LambdaMART 实验记录](experiments/ltr-fusion-v1.md) | 历史模型、数据与实验；不能把各阶段指标混作同一对照 |
| 旧 Golden 构建与评价口径 | [Golden V2](plans/golden-v2-realistic-evaluation.md) | 旧数据设计，不是当前 NevIR 输入说明 |
| Query 重写及分流方案 | [重写配对基准](experiments/query-rewrite-benchmark-v1.md) · [软分流候选](experiments/query-soft-routing-candidates.md) | 旧基准、候选设计与当时验证，非当前默认方法 |
| R1/R2 标签、量表与来源材料 | [Robust Fusion 历史导航](archive/robust-fusion/README.md) | 原稿按 Git 历史追溯；旧状态、提交与曝光身份保留 |
| 重构前源码或被忽略的资产如何恢复 | [恢复说明](plans/runtime-simplification-2026-09-06.md#recovery) | 查原版本及既有备份范围，不据未跟踪状态删除数据 |
| monorepo 早期设计 | [设计归档](archive/README.md) | 历史架构，部分与当前隔离约束不同 |
| 遗留人工材料是什么 | [人工任务说明](../human_tasks/README.md) | 当前没有人工作业；遗留材料不构成新任务 |

## 更新放在哪里

进度改 `CURRENT_STATUS.md`；研究假设与设计改研究计划；每次已执行实验登记到[逐次实验台账](experiments/EXPERIMENT_LOG.md)，实际结果写对应报告；取舍依据写讨论记录；路径和用法改数据／模型／脚本／实验 README。本目录只调整选择入口，报告清单由[生成脚本](../scripts/build_report_index.py)维护，不在多处复制结论或整套方案。
