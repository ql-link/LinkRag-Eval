# Robust Fusion R2 source recovery v6 fail-closed 运行报告

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`  
> `source_protocol_id`: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6`  
> 运行状态：`SOURCE_RECOVERY_V6_ABORTED_FAIL_CLOSED`  
> 性质：outcome-aware source engineering recovery terminal；不是数据、measurement 或 Gate 结果。

## 1. 结果前封存

v6 在任何 v6 provider 响应前完成独立 EP-planned spec、code snapshot、preparation、lock 与 receipt。seal 复验 scientific prereg、未修改 parser、128-slot registry、v2–v5 全部 append-only 现场、v3/v4 两份诊断及 v5 失败报告，并用零网络、零 API key dry-run 检查 R→EP→E→C 请求与 substantive recovery。

- preparation manifest SHA-256：`91685d720b8340e963b72bce926d8d1f66a8b4f4771c6ae88e8d3d947e038091`
- preparation lock SHA-256：`adf31f707e8bda2d1a03eea9288adcaab4af62ccccbc38d5ff808ad4bbfe5704`
- preparation receipt SHA-256：`d055e15d915430fdb04113552e3ca49bcc7018027865265d7e1784f8db0436a8`
- inherited R2SRC-001 verification SHA-256：`c42ca93b2be36b29c83dcd869c7b36223be43731697ad4068a6ede5710406d9c`
- static endpoint/model contract SHA-256：`6ce4ded394edf182c111adb62797e1a49a646d4e22dac27cfe71f8baa7ecab4c`
- dry-run SHA-256：`fb5631a6ed7d5fdbf52de1e481a3f6bda5e0fa2091d5ab4c2df5bb4964f5933c`

静态 contract 只确认既有 DeepSeek chat-completions endpoint 与 `model=deepseek-v4-pro`、non-thinking、JSON mode 的请求结构；seal 前没有 probe provider。R2SRC-001 逐字节继承 v4 accepted row，独立 provenance 固定为 `deepseek-v4-flash`/v4；v6 未调用或替换 001。

## 2. 唯一正式运行

provider 接受并完成了 16 个 `deepseek-v4-pro` 请求，因此本轮不是 permanent model error，也没有降级到 Flash。

- R2SRC-002：R、EP、E 首次机械通过；C 前两次因 normalized 后等于 equivalent candidate 而失败，第三次机械通过；第一份完整对象通过原 parser 与全部排除后永久接受。proposal SHA-256 为 `78422c62b107f0aff7fe0c9c007fc66e51bff74f7e9c152ee1c04d432016b560`，generator provenance 为 Pro/v6。
- R2SRC-003：R 第一次因 reference 长度 27（冻结范围 35–130，interior target 60–90）失败，第二次通过；EP 与 E 首次通过；C 的 6 个完整响应逐字节同 hash，全部因 normalized 后等于 equivalent candidate 而机械失败。

R2SRC-003/C 第 6 个相同 response 触发冻结的 `(slot, stage, orchestration attempt, response hash)` breaker。最后顺序为 `REQUEST_DISPATCHED` → response archive fsync → `CALL_COMPLETED` fsync → `HARD_BLOCK` fsync → raise。命令退出码 1，runner 写 terminal 后停止；未自动重跑，未回退模型。

停止 response SHA-256：`ad1442fcd8238942a940dcb1c7b760a08661baa2d550d7252c3f0aac8480aea0`。

provider usage 合计为 prompt 10,835 tokens、completion 741 tokens、cache hit 1,920 tokens、cache miss 8,915 tokens，按既有记录口径估算 `$0.0049276`。cache 字段只作 provider usage 事实，不用于推断重复响应原因。

## 3. append-only live 制品

live root：`runs/robust_fusion/r2_source_recovery_v6/robust-fusion-r2-source-recovery-v6-20260829/`

| 文件 | 行数 | SHA-256 |
| --- | ---: | --- |
| `accepted_proposals_not_truth.jsonl` | 2 | `58a8c76007ea59429ba69e4b125432921cae99a0772651ed094f3b668724ff37` |
| `generator_provenance.jsonl` | 2 | `a14793ad427bdf50f5620096a3f6cbe113e69dcaef0a79c5b99a36ba5d0a7e93` |
| `attempt_scoped_stage_locks.jsonl` | 7 | `1861b60e0b8ff464e6b0495aa0131457a48a96c300d25dc60013cbe144c8d111` |
| `orchestration_attempts_not_truth.jsonl` | 1 | `143ccb54bedae5118928ea3eeeded6d74e69d0feb61d2e78813b09f9224a384a` |
| `call_audit.jsonl` | 34 | `88458690a3d62492ae52fae18e7937e8eb06cb4179bc8759dda2644c6fa86f02` |
| `response_archive_synthetic_only.jsonl` | 16 | `c0af5116daffa8e3925ec66eab8a105e554e318d841a90d994fbf18b86faf134` |
| `authorization_receipt_snapshot.json` | — | `1026f9cbdfbd7705884527e3cf913f0f2ad9844172bb2ab63b6f2dcd249e7e2e` |
| `inherited_r2src_001_hard_lock.json` | — | `c42ca93b2be36b29c83dcd869c7b36223be43731697ad4068a6ede5710406d9c` |
| `terminal_error.json` | — | `43c4cac567dcb89d95a3eefd37d46db08b51204c417518251c4db5248ee27fd4` |

accepted ledger 当前有 2/128：逐字节继承的 R2SRC-001 与 v6 首个完整通过的 R2SRC-002。它们不足以形成 formal 128-family data lock；R2SRC-003 的 stage locks 属于已终止 attempt，不能当作永久对象。

## 4. 科研与授权状态

本轮证明 EP→E 在 002/003 均可机械锁定，且 Pro model 字段被 endpoint 接受；但这不产生语义质量或 measurement 结论。停止原因只是在冻结 breaker 内无法取得 R2SRC-003/C 的唯一机械合格值，不能据此单因果归因。

没有运行 fixed data lock、E5、DistilUSE、人工包、finalizer、readiness、Gate A/B、Blind、Reranker、D1–D3、A0 或 M1。当前状态为 `SOURCE_RECOVERY_V6_ABORTED_FAIL_CLOSED_AWAITING_COORDINATOR_DECISION`；formal R2 data lock 未形成，Gate A 继续未授权。v6 live root 与所有先前版本必须永久 append-only，不得重跑或覆盖。
