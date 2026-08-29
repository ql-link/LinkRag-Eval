# Robust Fusion R2 DeepSeek 正文来源工程恢复规范 v6

> research_id: `ROBUST-FUSION-R2-2026-08-29`  
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6`  
> 状态：`AUTHORIZED_OUTCOME_AWARE_ENGINEERING_RECOVERY_READY_TO_SEAL`  
> 性质：看到 v2–v5 source implementation failure 后的 outcome-aware engineering recovery；不是 measurement outcome tuning，不修改 scientific prereg、数据结果、estimand 或 Gate。

## 1. 不可变边界与模型来源

v2–v5 的 preparation、code snapshot、live response、append-only ledger、terminal/stop 记录、v3/v4 两份诊断及失败报告永久只读。v6 使用独立 spec、code snapshot、preparation、lock、receipt 和 live root；任何 v6 provider 响应前必须完成 seal。

scientific prereg、冻结 parser hash、128 slots、44/42/42 配额、12-cell、R1 exact/template/5-gram、跨 R2 near-duplicate、128-family/256-candidate 固定分母、estimand、编码器角色及 measurement/Gate 门槛均不变。

v4 的 R2SRC-001 按 v5 相同规则逐字节复验并 hard-lock，绝不重新生成或替换；其 generator provenance 固定记录为 `deepseek-v4-flash`、source protocol v4。v6 从 R2SRC-002 的全新 orchestration attempt 开始；v5 的 R2SRC-002/R 仅属已终止 attempt，不继承。

R2SRC-002…128 的 provider 固定为同一已授权 DeepSeek endpoint 的 `deepseek-v4-pro`，请求统一为 non-thinking、JSON mode、stream=false、`temperature=0.6`、`top_p=0.9`、`max_tokens=4000`。不得按 slot/attempt/输出换模型或采样参数，不得在永久 model error 后自动降级到 Flash。每个最终 accepted object 必须通过独立 provenance ledger 保存 generator model、protocol、slot 与 proposal hash；001 的 accepted row 保持逐字节不变。

## 2. 固定 R→EP→E→C orchestration

每个新 slot 的完整 attempt 顺序固定为 R→EP→E→C。所有 stage lock 只在当前 orchestration attempt 有效；attempt 放弃后不得复用。

### R

R 生成当前 slot 的 query/reference，沿用 v5 的固定语言、长度、schema、R1/跨 R2 排除和 substantive recovery。只发送固定 slot 元数据和新 synthetic microfact 指令。

### EP：rewrite plan

EP 只接收当前 attempt 的 query/reference，严格返回：

```json
{"operation_type":"...","source_span":"...","replacement_span":"..."}
```

机械门禁：exact keys；三个字段均为非空字符串；`source_span` 在 reference 中逐字节恰出现一次，且不是完整 reference；`replacement_span` normalized 后与 source span、reference 均不同；source/replacement normalized 长度均小于 reference 的 75%；replacement 使用冻结语言；不得出现 `equivalent_candidate` 或完整候选字段。

operation_type 按 edit_strength 冻结：

| edit level | 允许 operation_type |
| ---: | --- |
| 1 | `lexical_substitution`, `local_phrase_reorder` |
| 2 | `phrase_substitution`, `local_clause_reorder` |
| 3 | `clause_reorder`, `clause_split`, `clause_merge` |
| 4 | `multi_clause_rewrite`, `global_syntax_rewrite` |

EP plan 只是待执行的表面改写计划，不是真值，不得含 R1、Blind、生产/内部数据或完整候选。首个机械合格 plan 仅在当前 attempt 锁定。

### E：apply plan

E 只接收当前 attempt 的 query/reference、锁定 EP 三字段、冻结 edit band 和 changed-character interval。模型必须按 plan 自行生成唯一字段 `equivalent_candidate`；程序禁止应用 replacement、重写、扩写、截断、翻译或修复任何模型字符串。

E 输出仍由未修改 parser 口径检查语言、长度、四文本 normalized uniqueness、edit distance、R1 与已接受 R2 near-duplicate。命题等价最终只能由后续双人盲审确认，模型、EP、construction role 均不是真值。

同一 EP plan 最多接收 6 个完整 E responses。第 6 个仍机械失败时，先保存 response、`CALL_COMPLETED` 与整个 attempt 的失败记录，再放弃当前 attempt，从同一固定 slot 的全新 R 开始；不得更换 slot或复用 R/EP。E 的第六次失败是 attempt-level recovery，不触发 command-level identical hard block。

### C

C 沿用 v5 substantive recovery，不引入 live 可选的 plan 化分支；只改变冻结 conflict_type 的唯一事实槽，其他事实不变。C 输出仍经未修改门禁。

## 3. 结果前固定 recovery 与 breaker

每次 request 包含 numeric orchestration/response attempt、上一机械 failure enum/detail/必要 metrics 和冻结 strategy；不得包含失败正文。R/C 使用 v5 四策略循环；EP 使用按 edit level 固定的 operation_type 循环；E 使用 `apply_plan_exactly`、`apply_plan_with_minimal_grammar_adjustment`、`apply_plan_then_local_reorder`、`apply_plan_with_preservation_self_check` 四策略循环。策略只能由 stage、edit level、attempt index 与 failure enum 机械决定。

- R/EP/C 同一 `(slot, stage, orchestration attempt, response hash)` 第 6 次相同响应：command-level fail-closed。
- 任一 stage 在当前 attempt 累计 24 个完整 response 仍无新 lock：command-level fail-closed；E 的 6-response plan exhaustion 先行并转入新 attempt。
- 同一 slot 累计 24 个 orchestration attempts 仍无最终 accepted object：command-level fail-closed。
- 连续 8 次 transport/429/5xx、永久 provider/model、安全或封存漂移：立即 fail-closed。
- 第一份通过原 parser、R1/跨 R2 排除和全部机械门禁的完整对象立即永久锁定；不得请求第二份合格对象或择优。

## 4. crash-consistent 审计顺序

每次 provider 返回依次执行：`REQUEST_DISPATCHED` append+fsync → response archive append+fsync → 机械判定 → `CALL_COMPLETED` append+fsync → 可选 `HARD_BLOCK` append+fsync → raise。合法的 E plan exhaustion 在 `CALL_COMPLETED` 后追加 attempt-abandoned 记录并开启新 attempt，不伪装成永久 hard block。provider usage/cache 字段按返回值记录；无直接证据不得推断 cache 因果。

发送范围仅为固定 slot 元数据和当前 slot 内由 DeepSeek 刚生成、后续 stage 必需的 synthetic query/reference/EP/equivalent。禁止 R1、Blind、Gate、生产数据、内部正文、模型分数或人工结果。

## 5. 成功后的固定顺序

128/128 后才运行 fixed data/exclusion/quota lock；随后单次本地 E5/DistilUSE并生成物理隔离 relation A/B 与 similarity A/B 盲包。两名研究员各 relation 256 + similarity 256 = 512 行，到此停止。

人工提交前禁止 finalizer/readiness/Gate A/B；Blind、Reranker、D1–D3、A0/M1 继续禁止。不得 commit/push。
