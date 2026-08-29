# Robust Fusion R2 source recovery v4 fail-closed 记录

> research_id: `ROBUST-FUSION-R2-2026-08-29`  
> 状态：`SOURCE_RECOVERY_V4_ABORTED_FAIL_CLOSED_AWAITING_RECOVERY_DECISION`  
> 分类：source implementation/provider prompt interaction；不是数据质量、measurement、编码器、人工、readiness 或 Gate 结果。

## 结果

v4 已在任何 provider 响应前封存，随后只执行一次正式命令：

```text
PYTHONPATH=src:. .venv/bin/python scripts/run_robust_fusion_r2_source_recovery_v4.py execute --authorization-receipt docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json --allow-paid-api
```

命令 exit code 为 1；冻结 circuit breaker 报错 `non-financial hard block: repeated identical response`。没有命令级自动重跑。

R2SRC-001 在 R/E/C 分别使用 1/2/1 个完整响应后，第一个完整机械合格对象被永久接受。R2SRC-002 的 R 阶段使用 1 个响应取得 attempt-scoped lock；E 阶段随后得到 6 个相同 response hash，触发同一 slot/stage 相同响应六次的硬阻塞。停止时共有 11 个完整响应、21 个 audit event、4 个 attempt-scoped stage lock、1 个完整 assembly 和 1 个 accepted proposal。

最后一个响应已先写入 response archive 并 fsync；breaker 随后触发，故它没有对应的 `CALL_COMPLETED` audit，audit event 数为 21 而非 22。这是冻结执行顺序，不是响应丢失。全部 ledger 在停止后再次 fsync，未修改内容。

token/cost 只作审计：prompt 5,871、completion 479，按冻结 peak price 估算 `$0.002561184`。费用不是停止原因。

## 结果前封存

- preparation manifest：`01b32fc16758418cb6dc2659bc61560786fd7018d307cff5ef81198401dd99cf`
- preparation lock：`9b6d9b479fdac01209efbe3efaefb44bf823178fbeda17cc9f3ea4a4c73184ce`
- preparation receipt：`02c58a5b406fb0ab90a2b497b6fa8e9c507f5f24e2e626653b1bbb07cfdd31f1`
- zero-network dry-run：`3b758b65897b1b58aee5b7c25c0594bfc1dc5a04a562467d3fd9f022be7ed7ff`
- frozen parser：`34ba67706fb5ddb0b7ac7924b153e00c8f26ca34f60914bd31cdf7efd57de65c`
- scientific prereg manifest：`b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b`
- 128-slot registry：`c717641388cf0264ff75b17bec4d4b986a32a309fc6dfe8ab7b13ccbafc29f37`

seal 时 v4 live root 不存在、network calls 为 0、API key 未读取。v2/v3 与 v3 diagnostic 的 append-only hash 全部通过。

## v4 live 制品

根目录：`runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829/`

| 文件 | SHA-256 |
| --- | --- |
| `authorization_receipt_snapshot.json` | `f1ddcef8e4e9770d9d6f968b6e75068e60abb6a0776646963d25dceb2cc3f635` |
| `call_audit.jsonl` | `3c3cb03dc85eed353d0a2c6c01d5d58c66f67754b12b4faae3955d8f136a3a86` |
| `response_archive_synthetic_only.jsonl` | `8f0d2cea12e97587d3d54728d3ab0323a9a515d0653d34b934be0c70ae1b6111` |
| `attempt_scoped_stage_locks.jsonl` | `a06f09597055819540ea72ced30bdd986e3640a6f58be0d2dc9a1270fbe52842` |
| `complete_assembly_attempts_not_truth.jsonl` | `1f9964fe8ffc473bac85b0333c552c4e06f562c18f4aa9b9b9bff4292d93a43e` |
| `accepted_proposals_not_truth.jsonl` | `d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b` |
| `terminal_error.json` | `c192fc455f0e8d26a48717ab1ff5150e3e032eb0fe239e21dcb75934561acae0` |

## 科研边界与下一动作

没有形成 128-family data lock，不得把唯一 accepted proposal 用作正式 R2 Dev 或挑选证据。未运行 E5/DistilUSE、人工包、finalizer、readiness、Gate、Blind、Reranker、D1–D3、A0 或 M1。

v4 live root、代码快照、响应与失败记录永久只读保留。当前唯一下一动作是由协调方决定是否批准新的、结果前封存的版本化恢复；在此之前不得再次调用 provider。

后续只读诊断确认六个请求仅在 `stage_call` 审计字符串上变化、六个响应均机械失败于 equivalent normalized 后等于 reference；breaker 实际不含 orchestration-attempt 作用域。详见[R2 v4 只读结构诊断](robust_fusion_r2_source_recovery_v4_diagnostic_2026_08_29.md)。
