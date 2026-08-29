# Robust Fusion R2 source recovery v4 只读结构诊断

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> 状态：`FAIL_CLOSED_NON_SEMANTIC_SOURCE_IMPLEMENTATION_DIAGNOSTIC_AWAITING_V5_DECISION`
> 本报告不输出正文、不评价等价或冲突语义，也不形成数据质量、measurement、编码器、人工、readiness 或 Gate 结论。

## 1. 请求是否相同

冻结代码重建的六个非密钥 payload SHA-256 与 live archive 的 request hash 逐项一致。六个完整 payload 和 `messages` hash 各自不同；但移除 user message 中唯一变化的 `stage_call` 后，六个 payload 得到同一个 SHA-256 `bdb4ac9cadc708899a29de42e3b04501b21c56917a13719b5e738c3cd216ef77`。因此它们不是字节级相同请求，但生成约束、reference、采样参数和推理设置完全相同，唯一变化是审计身份字符串中的 E 响应序号。

| E attempt | payload SHA-256 | messages SHA-256 | response SHA-256 |
| ---: | --- | --- | --- |
| 1 | `a4d780296dfe34c9f04bd6e916cbbc9910c9298fd8f8d43299754a0cf8b8f15e` | `978808c4a5c59cf4659a0f32e74877aac37110d76445498b25967bc2593168ed` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |
| 2 | `1334b13e24c3a4ee74632cb59d33ed421c1bfd70108e93b67474f12c8b8c40b3` | `bdb6b9e7f2f4a4e7c5e2c67757bafa2696fa1a7f54d4aa3379ac22a996a2d2df` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |
| 3 | `2815fe09b0166873b75a2d993a08092a0eced59dca2970840c47179b981d596c` | `14a08d912aa8c48295b8a4083997edd29d794f82fd6919178c6405605a601598` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |
| 4 | `f7c76ebd19c8946ad1f649e0d0c3d0871e0c03d22836e8d05e62756365941910` | `409be1b6cdb9da9de313228ec9c44639400920d2e9f8fd04637cdcc7ff9ea284` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |
| 5 | `64cfb2eb691e8842c93c6c29d1611a386b99549708d0b178c702b936def2d208` | `e05a2523946d33623257b396926cacaf6d202587392c6bd6a752084fdd873045` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |
| 6 | `f9648721fa494e980fc133367983109b85f9e9170d104e37f0e743ec39af426a` | `482357d8e73dd7c82f5301241fbdbb74f9f99909ac00b7551eb3bd4ccee8578f` | `922fe1b088b46314b8b7cad8f90c2145d148c82b6b385dde4a9852b121fe81f1` |

六次均为 `temperature=0.2`、`thinking={"type":"disabled"}`、`response_format={"type":"json_object"}`、`stream=false`；`top_p` 未进入 payload，实际 provider default 不可由现场确定。`orchestration_attempt=source-recovery-v4-attempt-0001` 与 `stage_call=...stage-e-0001...0006` 实际进入 user message；独立数值型 `stage_response_attempt` 没有进入，attempt 只编码在 `stage_call` 字符串。

E retry 没有携带上一失败类别，也没有随 attempt 改变同义替换/句法重排策略、采样参数或其他 deterministic diversification。换言之，request hash 不同主要是审计元数据不同，而非恢复动作不同。

## 2. 六个响应的机械诊断

六个 response SHA-256 完全相同。每次均：

- JSON object PASS；exact key `equivalent_candidate` PASS。
- E 阶段 response schema 按设计不要求重复 slot identity 字段；archive 中绑定的 slot=`R2SRC-002`、stage=`E`、orchestration attempt=1 均匹配请求。
- 中文语言 PASS；normalized length 为 45 chars，冻结 short-zh 35–130 PASS。
- 与 query normalized 不同 PASS；与 reference normalized 不同 FAIL。
- reference→candidate normalized Levenshtein 为 0.0，edit level 1 的 `[0.02,0.18]` FAIL。
- R1 exact、template、5-gram near-duplicate 均无命中；与已永久接受 R2SRC-001 的跨槽 exact/template/5-gram 也无命中。

按冻结阶段 validator 的顺序，六次首个机械子原因均为 `equivalent_candidate_equals_reference`。本诊断没有判断该文本在语义上是否等价。

## 3. cache/context 证据边界

保存的 usage 显示六次 prompt/completion 都为 565/37 tokens。前两次 cache hit/miss 为 0/565；第 3–6 次为 384/181。runner 每次新建 client，并且发送的 messages 只有固定 system 和当次 user message，没有对话历史。响应 header 没有保存。

这些数据只能证明 provider 报告了部分 prompt-token cache 命中，不能证明 identical output 是由 cache、确定性解码、模型偏好或服务端其他机制导致；因果结论为 `UNKNOWN`。

## 4. breaker 与 crash-consistent audit

实际 response counter key 是 `(slot_id, stage, response_sha256)`，**不含** `orchestration_attempt`。因此它不是“同 slot+stage+orchestration attempt”作用域，而是跨该 slot/stage 的所有 assembly attempts 累计。在本次现场，六个响应碰巧都属于 orchestration attempt 1，所以该差异没有改变本次触发结果，但会影响未来多 attempt 行为。

执行顺序为：`REQUEST_DISPATCHED` audit → provider 返回 → response archive+fsync → identical-response breaker → stage validation → `CALL_COMPLETED` audit。第六个响应先被可靠保存，breaker 随即抛错，所以最后只有 `REQUEST_DISPATCHED`，没有 `CALL_COMPLETED/HARD_BLOCK`。未来 v5 应在 raise 前追加并 fsync 明确的 terminal `CALL_COMPLETED`/`HARD_BLOCK` 事件，或采用等价的两阶段 call-state 记录；这属于 crash-consistent audit 修正，不得回改 v4。

## 5. 最小 v5 继承判断

正式 128-family source data lock 尚未形成，但 v4 已按封存规则把 R2SRC-001 的“第一个完整机械合格对象”写入永久 accepted ledger。对同一 R2 重新调用 R2SRC-001、产生替代对象，会在已看到一个合格对象后重新开放选择，违背 first-complete-object lock。因而保守推荐不是从 128 个 slot 全量重放，而是：

1. 新建并结果前封存独立 v5 spec/code/preparation/live root；
2. 以精确 hash 导入 R2SRC-001，作为唯一永久 accepted predecessor，并让后续跨槽排除看见它；不得重新调用或替换；
3. R2SRC-002 的 R lock 只是 v4 orchestration attempt 内临时锁，v4 终止后不得继承；v5 应从 R2SRC-002 的全新 R→E→C attempt 开始，然后继续 R2SRC-003…128；
4. v5 修复 retry payload、breaker scope 和 terminal audit 后再封存；未获协调方批准前不得调用。

若要丢弃 R2SRC-001 并全量重放，较严谨的路径应是另立研究身份并预先声明 v4 整批失效，而不是在当前 R2 内静默替换；这不是最小恢复，也尚未获授权。

## 6. 机器制品

根目录：`runs/robust_fusion/r2_source_recovery_v4_diagnostic_v1/robust-fusion-r2-source-recovery-v4-diagnostic-v1-20260829/`

- request metadata SHA-256：`d303cc831bd386b71372e1b9a5f8735996457febb1a0d96911f8f21f322cae22`
- response mechanical diagnostic SHA-256：`76b4fd2f1f79753a63097006fd3294c2f9998d025ae8cc9a06502921d6d6bb01`
- summary SHA-256：`3f90b6467df8f60d06a5fb7db66f79abe174e1e6fffbc307cbf0aa6bf0ace2bd`
- manifest SHA-256：`46483eb3945113865f3f90465169af88a0186f7dce5a5fd014ac992d02098063`
