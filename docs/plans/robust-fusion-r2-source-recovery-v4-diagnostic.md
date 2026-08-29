# Robust Fusion R2 source recovery v4 只读结构诊断计划

> 状态：`OUTCOME_AWARE_NON_SEMANTIC_IMPLEMENTATION_DIAGNOSTIC`  
> 目的：解释 R2SRC-002/E 的 identical-response breaker；不形成数据质量、measurement、编码器、人工、readiness 或 Gate 结论。

## 固定输入

只读输入限定为：

| 输入 | SHA-256 |
| --- | --- |
| v4 preparation manifest | `01b32fc16758418cb6dc2659bc61560786fd7018d307cff5ef81198401dd99cf` |
| v4 frozen code snapshot `r2_source_recovery_v4.py` | 从上述 manifest 逐项校验，不另行猜测 |
| `call_audit.jsonl` | `3c3cb03dc85eed353d0a2c6c01d5d58c66f67754b12b4faae3955d8f136a3a86` |
| `response_archive_synthetic_only.jsonl` | `8f0d2cea12e97587d3d54728d3ab0323a9a515d0653d34b934be0c70ae1b6111` |
| `attempt_scoped_stage_locks.jsonl` | `a06f09597055819540ea72ced30bdd986e3640a6f58be0d2dc9a1270fbe52842` |
| `complete_assembly_attempts_not_truth.jsonl` | `1f9964fe8ffc473bac85b0333c552c4e06f562c18f4aa9b9b9bff4292d93a43e` |
| `accepted_proposals_not_truth.jsonl` | `d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b` |
| `terminal_error.json` | `c192fc455f0e8d26a48717ab1ff5150e3e032eb0fe239e21dcb75934561acae0` |
| R1 exclusion registry | 由 v4 preparation manifest 已锁条目逐项校验 |

不得修改或补写任何 v4 文件，不得恢复调用、生成新正文、评价语义或输出 response text。诊断输出只允许 hash、键集合、slot/stage/attempt 元数据、参数、长度、normalized uniqueness、edit ratio/band、R1/跨 R2 exclusion 和 audit 顺序。

## 诊断问题

1. 用冻结 code snapshot 的纯函数和同 attempt stage lock 重建六个 E payload；逐个比对完整非密钥 payload hash 与 live request hash，并计算 messages hash。报告 temperature、top_p、thinking、response_format、stage response attempt 等是否真正进入发送 body。
2. 对六个响应逐项计算 JSON object、exact key、响应是否预期携带 identity、语言、长度、与 query/reference 的 normalized 唯一性、reference→candidate normalized Levenshtein、edit band、R1 exact/template/5-gram 和已接受 R2 跨槽排除。不得作 equivalent 语义判断。
3. 核对 retry body 是否含上一机械失败类别、attempt index 或 deterministic diversification。provider cache/context 只使用已保存 usage/header；未保存或无法归因则记 `unknown`，不得借外部文档猜测本次请求行为。
4. 从冻结源码确认 repeated-response breaker 的真实 key 作用域，以及 response archive 与 `CALL_COMPLETED` audit 的写入顺序。只提出未来版本的 crash-consistent audit 修正，不修改 v4。
5. 对 v5 的“继承 R2SRC-001”与“新 root 全量重放”分别评估 scientific prereg、尚未形成 formal source data lock、first-complete-object lock、append-only 和选择偏差边界；只给保守推荐，v5 保持未授权。

## 输出

脚本必须确定性地写入全新 diagnostic root，输出 machine JSON/JSONL、manifest、SHA-256 sidecar 和人读报告；同 root 重放拒绝。v4 live、v4 preparation、v2/v3、R1、Blind 均只读。
