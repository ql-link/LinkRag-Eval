# Robust Fusion R2 source recovery v5 fail-closed 运行报告

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`
> `source_protocol_id`: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v5`
> 运行状态：`SOURCE_RECOVERY_V5_ABORTED_FAIL_CLOSED`
> 性质：source implementation terminal；不是数据、measurement 或 Gate 结果。

## 1. 结果前封存

v5 在任何 v5 provider 响应前完成独立 preparation、code snapshot、lock 与 receipt。seal 复验了 scientific prereg、未修改 parser、128-slot registry、v2/v3/v4 现场和 v3/v4 两份诊断的固定哈希，并以零网络、零 API key dry-run 检查 substantive retry payload。

- preparation manifest SHA-256：`6d01a708a1d30ceace22ac17223a3d8047751fb1df675eb7fa061e87a91bc038`
- preparation lock SHA-256：`d55ccccbc9a6a540b22227c2cafe5af11e4f008c3c14be43149b99e561b2b165`
- preparation receipt SHA-256：`66631541053704f3085393bda77a8c649868b3b18643f252231f37ac71bfa779`
- inherited R2SRC-001 verification SHA-256：`b347b929aa7bfd949d84cbce2e37ee106ba4ad127e1039d3600d5c0c244fde2a`
- dry-run SHA-256：`bba4025c5d51b8dc359dbc421c8711d8f37c6187068f893af3841fe6b078514a`

R2SRC-001 经 accepted row、source object、assembly、slot identity、stage locks、原 parser 与全部机械门禁重放后，以逐字节相同的 v4 accepted ledger hard-lock 继承；v5 未对它发出 provider 调用。R2SRC-002 未继承 v4 的 attempt-scoped R 值，正式 v5 从新的 R 阶段开始。

## 2. 单次正式运行

唯一一次 v5 命令完成 11 次 provider 返回：R2SRC-002/R 第一次机械通过并仅形成当前 attempt 的 stage lock；随后 R2SRC-002/E 的 10 次完整响应全部因 `schema / equivalent_candidate_not_unique` 拒绝，机械诊断均为 normalized 后与 `reference` 相同。E 响应只出现两个 hash：

- `3b66d0c511fe2e8ac698683f2026b3ff6d7c98a1046f39f6a9fe86bc2002d4bd`：6 次；
- `3ec0d288d634b0c895490bb1de70f4346a2c1a39274807eb14e2a39ca7e6c1a3`：4 次。

第 10 个 E response 是第一项 hash 的第六次出现，因此触发冻结的 `(slot, stage, orchestration attempt, response hash)` identical-response breaker。账本顺序为 `REQUEST_DISPATCHED` → `CALL_COMPLETED` → `HARD_BLOCK`；第六次重复响应的 hash、usage 与机械 outcome 已在 hard block 和 raise 前 append+fsync。命令退出码为 1，runner 写出 terminal 后停止，未自动重跑。

provider usage 字段合计为 prompt 7,581 tokens、completion 451 tokens、cache hit 3,072 tokens、cache miss 4,509 tokens，按已存价格口径估算 `$0.002622288`。这些 cache 字段只作为 provider usage 事实记录，不据此声称重复响应由 cache 导致。

## 3. append-only live 制品

live root：`runs/robust_fusion/r2_source_recovery_v5/robust-fusion-r2-source-recovery-v5-20260829/`

| 文件 | 行数 | SHA-256 |
| --- | ---: | --- |
| `accepted_proposals_not_truth.jsonl` | 1 | `d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b` |
| `attempt_scoped_stage_locks.jsonl` | 1 | `db7fb342373d03abb1f1bc5db8937d7897f14d66745e4f5828a0481213cffced` |
| `call_audit.jsonl` | 24 | `39cdbffbd7b79c858c7908d9e479ebdbf838add46a029f5e449d07674157c2ba` |
| `complete_assembly_attempts_not_truth.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `response_archive_synthetic_only.jsonl` | 11 | `686b23926155baff47cc54b21e777e4792cb5e85b50919e4fd7ebee08af6c4d0` |
| `authorization_receipt_snapshot.json` | — | `cbe3909bda4f2d9e393a1b0256cb3077abca2d1ecedab66855150239c44123b1` |
| `inherited_r2src_001_hard_lock.json` | — | `b347b929aa7bfd949d84cbce2e37ee106ba4ad127e1039d3600d5c0c244fde2a` |
| `terminal_error.json` | — | `5d8e88cbae6f12fb0ebe986415053bed514e0989bb4c0a4d23372e03ae46e3df` |

accepted ledger 仍只有继承的 R2SRC-001，尚未形成 128-family formal source data lock；R2SRC-002/R 的 stage lock 随本次已终止 orchestration attempt 失效，不能当作永久 accepted proposal。

## 4. 科研与授权状态

本次失败只说明冻结的 v5 source implementation 未能在 breaker 内取得 R2SRC-002 的 E 阶段机械合格值。没有运行 E5、DistilUSE、人工包、finalizer、readiness、Gate A/B、Blind、Reranker、D1–D3、A0 或 M1；没有生成 measurement 或 Gate 结果。

当前状态为 `SOURCE_RECOVERY_V5_ABORTED_FAIL_CLOSED_AWAITING_COORDINATOR_DECISION`。formal R2 data lock 未形成，measurement 未开始，Gate A 继续未授权。v5 live root 和所有先前版本必须保持 append-only，不得重跑本命令或覆盖制品。
