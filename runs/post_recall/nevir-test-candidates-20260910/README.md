# 官方 Test 候选快照：#23 补交，#19 验收

2026-09-11 已接收负责人提供的 `LinkRag-Eval-Issue23-Test-Snapshot-20260911/`。先将原 `snapshot/` 移入本目录，再进行离线验收；原 README、SHA256SUMS、脚本和成员终评文件保存在 [delivery-20260911/](delivery-20260911/)。30 个原文件全部保留，交付清单的 29 项校验在迁移前及验收后均通过。根目录的空交付文件夹已删除。

## 已验收内容

[run.json](run.json) 是本次接收方的聚合验收记录；[snapshot/run.json](snapshot/run.json) 是成员原采集记录，两者不互相覆盖。输入、候选、SQLite 和日志均在本地，受 Git 忽略；远端 Qdrant 向量未随包交付，固定候选终评不需要重新访问它们。

| 检查 | 结果 |
| --- | ---: |
| Test 查询／配对／来源组 | 2,766／1,383／700 |
| 唯一段落／候选行 | 2,081／421,953 |
| 两指定段共同进入三路并集 | 2,738/2,766（98.99%） |
| 两指定段共同进入固定融合 Top20 | 2,631/2,766（95.12%） |
| 共同覆盖且排除结构冲突后的主评价分母 | 2,736 查询／1,363 完整配对／699 来源组 |
| 与 Train／Validation 正文完全相同的段落 | 1／3，共 4 段，全部保留 |
| 两份 SQLite 完整性／语料行数 | 均 ok／2,081 |

原始 Test 版本为 NevIR `6263585072ce3b435ed09658613553fbf4e74184`。以本地原始 Test 在临时目录重建 corpus、passage mapping、queries、supervision，四份文件逐字节一致；候选契约、正文与三路运行参数检查通过。仅使现有输入校验器接受 `test` 角色，没有改变召回、训练或评价定义。

沿用 dataset **995301**、Qdrant 前缀 **eval_nevir_test_20260910**、用户分区常量 990001；编码器、召回深度 150／50／100、阈值 0.3／0.2、固定融合权重 0.70／0.15／0.15、BM25 FTS5 v2 与开发／确认口径一致。原 JSON 中成员机器的绝对路径保持原样；当前实际路径见接收方 run.json。

## 请求与中断记录

入库累计 2,337 次编码尝试（dense 256、sparse 2,081），保留 2 次 HTTP 400 和 4 次没有响应记录的 dense 请求；查询采集累计 5,536 次尝试（dense／sparse 各 2,768），另有 1 次 dense 请求没有响应记录。缺回执的结果为未知，不能记为成功或断言全都失败；累计次数包含恢复执行。两阶段最终状态均为 completed，原请求明细及 state 留在 `snapshot/{ingestion,candidates/test}/`，汇总进入本目录 run.json。本次没有新增远端请求。

## 实际验收与后续使用

```bash
.venv/bin/python runs/post_recall/nevir-test-candidates-20260910/accept_snapshot.py \
  --out runs/post_recall/nevir-test-candidates-20260910/run.json
```

上述命令已经执行，2026-09-11 13:04:50—13:06:06 UTC，75.184 秒，包含准备重建、契约和覆盖计算。输出已存在，脚本拒绝覆盖；它只做机器校验与聚合覆盖，不调用训练模型或判断器。完整非 integration 回归 1,310 passed、23 skipped、3 deselected，6 项既存 warnings；新脚本及相关改动 Ruff 通过。

**正式终评前不得人工或通过 Agent 查看 Test 单题文本、标签或逐题分数。** 程序可使用固定输入做准备与评价，但只展示聚合数。本次只重建既有融合分用于 Top20 选择／覆盖，未计算模型正确率。

[#19](https://github.com/ql-link/LinkRag-Eval/issues/19) 的本地快照交付已满足，已于 2026-09-11 13:30:00 UTC 按 completed 关闭；#20 随后已基于这些固定输入完成 Qwen／BGE 正式终评，结果与中断恢复记录见 [nevir-test-main-20260911](../nevir-test-main-20260911/README.md)。此前成员 E0／融合／N=8 的 [Test 聚合](../nevir-test-final-20260911/README.md) 保持独立：本次可核验其输入与覆盖，尚未重放成员模型评分，也没有补齐原冻结时间线。Test 已用于成员实验，不能称全局未曝光。
