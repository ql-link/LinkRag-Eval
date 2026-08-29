# P2-01 Dev 共同支持唯一补充周期预注册、发包与终审报告

> 状态：`P2_TERMINAL_INCONCLUSIVE_GATE_A_UNAUTHORIZED`
> 范围：唯一一次 pre-Gate Dev 共同支持补充；Gate A/B、Reranker 效果、D1–D3、A0 与 M1 均未运行。

## Material Passport

| 字段 | 值 |
| --- | --- |
| Material ID | `ROBUST-FUSION-SIMILARITY-SUPPORT-SUPPLEMENT-2026-08-29-v1` |
| Run ID | `internal-v6-dev-similarity-support-supplement-v1-20260829` |
| Verification Status | `VERIFIED_TERMINAL_INCONCLUSIVE` |
| 正式目录 | `runs/robust_fusion/similarity_dev_support_supplement_v1/internal-v6-dev-similarity-support-supplement-v1-20260829/` |
| 预注册 manifest SHA-256 | `81468fee2b117ca2a20cd21acb90654215a1ac8ae97851422dc7f355f63b1b1d` |
| 结果前 lock SHA-256 | `57179fbf6b44e4705535cf120177b65cbeb20cd48069fb4ba259b1ba5f6c6b2b` |
| 本地 lock receipt SHA-256 | `ad83a1fb8864454dbdb7e684f88fab7807a0a88f28105ca05a0edf57def20adc` |
| 数据 manifest SHA-256 | `077590541785605b9827b6bdbba28a5ac4a7631f04f44a230f4d7ff9e823b077` |
| 自动 manifest SHA-256 | `1c8b049932db6fdc2cef02583e9f8e5601be0a30064f86668d25ca97dd61327d` |
| 候选分数文件 SHA-256 | `e213e4b6231d87340ea0cb1272b7985f399d2c198f0547be197e0585dad73706` |
| 四提交 lock SHA-256 | `7a3ca4341858752fed1b1aa50c07d2797261325aeee52de3942a81351fc72ae6` |
| post-lock implementation manifest SHA-256 | `af35908b82c7d50095ec28642f5dd6e26c0bd83e37b37402757eeb41410499fb` |
| finalization manifest SHA-256 | `ea40f4f0380a35efd9212fb7b0ffd6c1f26be93634b99022ba9782a99b7f2b35` |
| finalization receipt SHA-256 | `3953e92e85a74695a505fa95d53ca3b825add981ca953fda8d9eab1a6d013465` |

## 1. v1 永久结论与补充周期边界

原 `similarity_dev_calibration_v1/internal-v6-dev-similarity-calibration-v1-20260829/` 的 28 个 family、A/B、仲裁、哈希与报告全部保持只读。其共同支持覆盖继续单独报告为等价 `5/28=17.86%`、冲突 `16/28=57.14%`，正式结论永久为 `INCONCLUSIVE`。本补充不覆盖、不筛除、不重新仲裁 v1，也不消耗 Gate A 的 Inconclusive 追加额度；P2 自身不再允许第三轮补充。

## 2. 固定样本量与结果前锁定

若新增项目全部命中，等价侧达到 combined 60% 至少需要 30 个新配对 family。这只是代数下限，没有功效余量。预注册把“某关系上的成功”定义为：该候选通过正式关系复核、分数存在，并落入最终 combined 的共同支持区间；关系无效、缺失或非有限分数均按 miss 进入固定分母。

规划替代假设取每侧成功率 `p=0.80`，目标为两侧同时达标概率的 Bonferroni 下界至少 0.80，不假设两侧独立。在 `28+n≤100` 的限制下，`n=72` 是第一个达到该目标的整数：

- combined 每侧固定分母 100，至少命中 60；
- supplement 等价侧至少命中 55/72，冲突侧至少命中 44/72；
- 在 `p=0.80` 时，两侧同时达标概率下界为 `0.8208882946`；
- 敏感性：`p=0.75/0.85/0.90` 时该下界为 `0.4517/0.9820/0.9998`。

`p=0.80` 是设计替代假设，不是成功保证。若真实联合构造/支持率只有 0.75，本上限不足以提供 80% 把握；预注册后果仍是 FAIL/INCONCLUSIVE，而不是降阈值或扩第三轮。

锁定顺序已经机器记录：预注册 manifest 与代码摘要先形成，lock 明示当时无 `data/automatic/human` 结果目录；候选物化与向量/分数 manifest 的纳秒时间均晚于 lock。lock 后生成器和评分器未再修改。

## 3. 新 Dev population 与自动制品

补充 population 固定为 72 个 calibration-only 确定性合成微事实 family，使用独立 `RF-SIM-SUP-*` 命名空间：

- 中文/英文各 36；short/long 各 36；
- 四类冲突各 18，每类 short/long 各 9；
- 每个 family 恰有一个唯一正确参照、一个等价候选和一个事实冲突候选；
- 同一 family 的两个候选使用同一表面模板，只在一个预注册事实值上不同；
- 构造角色不是人工真值，不能替代双审关系标签。

本地冻结模型共编码 216 条文本，生成 144 个 `S_qg(c)` 分数。E5 向量形状为 `216×768`，DistilUSE 为 `216×512`；第二次内存重放与已存两组向量均逐字节一致。144 个候选中 short/long 各 72；E5 截断 0，DistilUSE 仅 long 72 行发生冻结规则内截断。

构造角色口径的非正式预览为：supplement-only 两侧均 100%，combined 等价/冲突为 96%/99%，区间 `[0.9545807831, 0.9996898962]`。该预览只说明模板设计按预期形成表面匹配，不能替代正式关系标签，也不能冻结 combined 数值。

## 4. 人工职责、负荷与盲化

每名研究员共有 192 行、分成两个物理隔离任务：

1. `human_relation/annotator_a|b/`：每人 144 行。依据标注手册 v2 独立判断参照有效性、目标组唯一性、`target_relation` 与 `conflict_type`；不填写语义相似度。
2. `human_similarity/annotator_a|b/`：每人 48 行。只按与 v1 相同的 1–5 量表判断两段文本接近程度；不判断哪段正确，不填写关系标签。

两类包均不含模型分数、分带、构造角色、补充周期希望改善哪一侧或答案键。相似度 48 行按 `construction role × short/long` 四格各 12，并由锁定算法在每格抽取 E5/DistilUSE percentile-gap 的低/高端各 6。关系包覆盖全部 144 个候选，不以分数抽样。

唯一操作方式如下：研究员 A 只使用两个 `annotator_a` 目录，研究员 B 只使用两个 `annotator_b` 目录；各自将 `submission_template.csv` 复制为同目录 `submission.csv`，保持表头、ID、行数和 `adjudication_status=single` 不变，独立填完后只通知主持人。不得互看、讨论或访问任何 `facilitator` 目录。四份文件必须同时存在后，主持人才运行：

```bash
PYTHONPATH=src .venv/bin/python scripts/review_robust_fusion_similarity_support_supplement.py lock-submissions
PYTHONPATH=src .venv/bin/python scripts/review_robust_fusion_similarity_support_supplement.py validate
```

初始提交审阅器 SHA-256 为 `e0e1ce2082a15f6e4f033b1010d489c069e9432bd09a840ddabe6bf9de6d406e`。它先仅哈希锁定四份提交，再读取和机械校验；关系分歧/不确定全部仲裁，相似度分差至少 2 或任一不确定为强制仲裁，其他非完全一致项也仲裁以获得唯一最终分数。实际四份提交先锁后验，关系 144/144、相似度 48/48 均完全一致且全部 `uncertain=no`，三类仲裁集合均为空。

## 5. 唯一终止与当前状态

正式 combined 分析无条件保留 v1 的 28+28 条合格项，并按 intent-to-calibrate 规则保留本轮固定 72-family 分母。必须分别报告 v1、supplement-only 和 combined；只有 combined 共同支持、supplement-only 人工效度和 v1+supplement combined 人工效度全部 PASS，才一次性冻结 `ddof=1` 标准化与 q25/q75、q30/q70、q20/q80 数值，并进入 readiness 复核。

任一 combined FAIL/INCONCLUSIVE 都使 P2-01/P2-04 继续未完成、Gate A 继续未授权，且不得追加第三轮。真实终审结果为 `INCONCLUSIVE`，因此没有生成 `formal_numeric_freeze.json`，唯一合法状态为 `P2_TERMINAL_INCONCLUSIVE_GATE_A_UNAUTHORIZED`。

## 6. 过程偏差台账：未到时点的 outcome-blind readiness 写入

在 P2 补充人工提交尚未完成、尚未到 readiness 正式复核时点时，为诊断 readiness 单元测试及协议版本对齐问题，曾调用 outcome-blind Gate A readiness CLI 入口 `scripts/audit_robust_fusion_gate_a_readiness.py`。该入口只面向协议、控制 manifest、checksum、Git 状态和制品存在性，不读取确认性排序结果；但其默认写入行为意外生成了以下正式 runs 路径：

`runs/robust_fusion/gate_a/readiness-preflight-v4.json`

发现后，该文件被移入本机废纸篓，目标位置为 `/Users/kawauso/.Trash/linkrag-eval-readiness-preflight-v4-accidental-20260829.json`；本次收口已确认正式 `runs/robust_fusion/gate_a/` 中不再保留 `readiness-preflight-v4.json`。不得恢复该废纸篓文件用于补充取证。可用记录只支持以下时间与摘要边界：

- 移出前 shell 列表曾观察到文件系统修改时间为 `2026-08-29 16:48`（Asia/Shanghai）；这只是文件元数据，不等于精确调用时刻；
- 精确调用时刻：`unknown`；
- 原文件 SHA-256：`unknown`。

此次调用没有读取任何确认性排序结果，没有运行 Gate A 或 Gate B，也不构成 Gate 证据或 Gate 样本消耗。文件移出后，readiness 版本对齐只通过纯函数 `build_report(...)` 与相关单元测试验证，没有再次调用会写正式 preflight 的 CLI 入口。当时 v1 的 `INCONCLUSIVE`、本补充的 `AWAITING_HUMAN_SUBMISSIONS`、P2-01/P2-04 未完成以及 Gate A 未授权均保持不变；后续真实人工终审得到的 terminal `INCONCLUSIVE` 同样不授权 readiness 或 Gate。

防回归约束：在 P2 的四份正式人工提交完成、锁定、校验与仲裁并达到正式 readiness 复核时点之前，readiness 验证只能调用纯 `build_report(...)` 或相关单元测试；不得调用会向正式 runs 写入 `readiness-preflight-v4.json`（或后续版本 preflight）的 CLI 入口。

## 7. 锁后缺失执行器、单次终审与唯一结论

四份提交完成锁定与 `validate` 后，机械结果显示关系 144/144 完全一致、相似度 48/48 ordinal 完全一致、全部 `uncertain=no`，无需召集仲裁员；但当时的 CLI 只有 `lock-submissions` 与 `validate`，缺少“零仲裁直接终审”执行器。这是已冻结 protocol 的实现缺口，不是 protocol、estimand、编码器、分母、missing-as-miss、`ddof`、共同支持定义、60% 门槛、六项人工效度门槛或停止规则的变更。

在读取真实终审结果前，新增执行器先用纯合成 fixtures 覆盖零仲裁成功、差异/不确定拒绝、提交/预审/哈希漂移拒绝、固定分母 missing-as-miss、60% 边界、任一人工效度失败阻断、构造角色不形成真值和重复运行拒绝覆盖。随后独立封存：

- implementation spec SHA-256：`7ab251c1818148f84d1ea5989bf26f19be83595495f6a5bad82d0660d2ee8ea3`；
- code snapshot SHA-256：`3fde23b918231930ef8f5064121f1cb63e90e1685aec08e668fd22ece3b6ec3a`；
- implementation manifest/receipt SHA-256：`af35908b82c7d50095ec28642f5dd6e26c0bd83e37b37402757eeb41410499fb` / `b3bda9c79a978a30ccdf4cddb032d4c18e47ac4e278d154e1414f43a5e5d3a6b`。

spec 明确只取 A/B 完全一致共同值，任一差异、`uncertain=yes` 或锁、manifest、ID、行数、预审哈希漂移均 fail-closed；`construction_role` 只标识预注册固定分母槽，不是关系真值，`automatic/construction_role_preview.json` 未被解析或用于判定。代码封存后，真实 finalizer 只运行一次并成功生成 append-only `human_review/facilitator/finalization_v1/`：

| 范围 | 结果 |
| --- | --- |
| v1 共同支持 | 区间 `[0.9843160362, 0.9955983803]`；等价 `5/28=17.86%`、冲突 `16/28=57.14%`；FAIL，永久 `INCONCLUSIVE` |
| supplement-only 共同支持 | 区间 `[0.9762563922, 0.9991891847]`；等价 `48/72=66.67%`、冲突 `54/72=75.00%`；PASS |
| combined 共同支持 | 区间 `[0.9545807831, 0.9996898962]`；等价 `96/100=96.00%`、冲突 `99/100=99.00%`；PASS |
| supplement-only 人工一致性 | 48/48 exact；QWK `1.0`，±1 `100%`；PASS |
| supplement-only 六项效度 | E5 overall/short/long=`0.1775/0.3250/0.3612`；DistilUSE overall=`0.4512`；最高带中位数/≥4 比例=`5.0/100%`。E5 overall 未达 `0.50`，结论 `INCONCLUSIVE` |
| combined 人工一致性 | 69/72 exact；QWK `0.9740`，±1 `100%`；PASS |
| combined 六项效度 | E5 overall/short/long=`0.3968/0.4237/0.4703`；DistilUSE overall=`0.5010`；最高带中位数/≥4 比例=`4.0/100%`。E5 overall 未达 `0.50`，结论 `INCONCLUSIVE` |

唯一联合规则要求 combined 共同支持、supplement-only 人工效度与 combined 人工效度三者全 PASS；本轮只有共同支持 PASS，故正式结论为 `INCONCLUSIVE`。final decision、共同支持、人工效度、manifest 与 receipt SHA-256 分别为 `204c008c…a7e9d`、`721fa49c…3d980`、`2a496d6f…e18b3`、`ea40f4f0…f2b35` 与 `3953e92e…13465`。没有生成正式标准化或分带数值；P2-01/P2-04 未完成、Gate A 未授权且未执行，P2 不得开启第三轮补充。
