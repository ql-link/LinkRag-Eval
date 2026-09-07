# 召回后实验产物入口

查实验先读下表对应目录的 `README.md`，再按需打开结果文件。数据划分与六个实际输入见[数据入口](../../data/README.md)，当前工作安排见[当前状态](../../docs/CURRENT_STATUS.md)；本页不另定实验计划。

## 与当前英文研究直接相关的四个实验

| 实验及目录名 | 做了什么／如何使用 | 一页说明 |
| --- | --- | --- |
| 英文特征对照 `nevir-english-features-20260907/` | legacy 控制与英文适配各训练一次；英文模型产自这里 | [对象、结论与文件](nevir-english-features-20260907/README.md) |
| 英文模型诊断 `nevir-english-diagnostic-20260907/` | 原 A 与英文模型在同一开发候选上重放、追踪；未训练 | [对象、结论与文件](nevir-english-diagnostic-20260907/README.md) |
| 历史同特征重训 `nevir-ltr-validation-20260907/` | 原 A 对历史 B；其保存的 Train／开发候选仍被复用 | [共享输入与历史产物](nevir-ltr-validation-20260907/README.md) |
| 历史 A/B 诊断 `nevir-offline-diagnostic-20260907/` | 旧特征下的 A/B 机械诊断及原盲审材料 | [历史诊断文件](nevir-offline-diagnostic-20260907/README.md) |

`features` 实验回答“基础英文适配是否改善开发表现”；`diagnostic` 实验检查“已有模型如何在这些候选上打分”。两个目录不能互当结果来源。模型身份统一查[模型入口](../../models/README.md)。

## 常见文件名怎么理解

| 文件或目录 | 实际职责 |
| --- | --- |
| `selection.json` | 训练输入、排除项、参数及选模记录；不是单纯的最终分数 |
| `manifest.json` | 含义取决于所属目录：模型包内是模型契约，诊断目录内是运行范围与状态 |
| `summary.json`／`comparison.json` | 所属实验的聚合统计；先看实验说明中的比较对象与分母 |
| `cases.jsonl`／`raw-predictions.jsonl` | 逐题分析／候选分数；不是人工金标，也不是可直接交给盲审者的公共材料 |
| `checks/` | 工程检查日志；与检索效果分开。其 README 可按旧文件名查新位置 |

## 其他历史目录

| 目录 | 用途 |
| --- | --- |
| [english-capability-20260907](english-capability-20260907/README.md) | 普通英文的端到端能力检查 |
| [nevir-suitability-20260907](nevir-suitability-20260907/) | NevIR 数据适用性审计 |
| [nevir-controlled-20260907](nevir-controlled-20260907/) | 最初 20 对 NevIR 问题复现 |
| [exploration-connectivity-20260906](exploration-connectivity-20260906/)／[direct](exploration-connectivity-20260906-direct/) | 早期探索链路连通性检查 |
| [sparse-prefix-probes-20260906](sparse-prefix-probes-20260906/) | Sparse 前缀探针 |
| [t2-full-20260906](t2-full-20260906/) | 暂停的 T2 入库及故障记录，不属于当前英文训练输入 |

这些历史目录和根级进程／咨询文件保留原位；不因存在旧脚本就恢复运行。

## 后续命名沿用这三个原则

- 实验目录写出数据集、实验目的和日期，例如 `nevir-english-feature-comparison-YYYYMMDD/`；不用 `new`、`final2` 或仅靠日期区分用途。
- 新文件名写出对象与内容，例如 `development-pair-metrics.json`、`english-training-selection.json`；只有组别已明确时才用简短名称。程序固定格式继续按现有接口，不擅自改名。
- 每次运行有一份短 README，写明问题、比较对象、数据范围、结论和关键文件；参数与逐题数据仍链接原产物，不复制。只建立实际需要的子目录。

本入口及上述四个实验的目录说明可纳入 Git；运行数据、模型、日志继续忽略。路径缺失时报告具体文件，不自动重建实验。
