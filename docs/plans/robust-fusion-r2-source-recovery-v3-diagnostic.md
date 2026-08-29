# Robust Fusion R2 source recovery v3 机械失败诊断计划

> 状态：`OUTCOME_AWARE_IMPLEMENTATION_DIAGNOSTIC`  
> 目的：解释 v3 source prompt/parser 交互为何 0 accepted；不形成数据、measurement 或 Gate 结论。

只读输入固定为 v3 live root 的 `call_audit.jsonl`、`response_archive_synthetic_only.jsonl`、空的 `accepted_proposals_not_truth.jsonl` 和 `coordinator_stop_decision.json`。输入正文只在本地机械计算中解析；输出不得包含正文，只保留 response hash、slot/attempt、字段长度、normalized 唯一性、语言判定、长度判定、reference→两候选 normalized Levenshtein、R1 exact/template/5-gram 命中和冻结 parser 顺序下的首个失败原因。

诊断必须回答：

1. 是否存在 JSON/schema/slot identity 问题；
2. 四文本唯一性失败的精确重复字段对；
3. 中文 short 长度使用 normalized 字符数是否与 prompt 一致；
4. edit strength 的数值区间与实现单位是否一致；
5. 冻结规则是否数学可满足，或只是 provider 未同时满足非复制与最短长度；
6. v4 最小方案只能改变 prompt orchestration/调用拆分，不得放宽 parser、阈值、slot、分母、R1 排除、estimand 或 measurement Gate。

该诊断禁止语义评价、内容择优、程序化改写、E5/DistilUSE、人工包、readiness、Gate、Blind 或新的 provider 调用。
