# Robust Fusion R2 DeepSeek 正文来源保守恢复规范 v5

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v5`
> 状态：`AUTHORIZED_RESULT_BEFORE_READY_TO_SEAL`
> 性质：source implementation recovery；不修改 scientific prereg、数据结果、measurement 或 Gate。

## 1. 永久只读与继承

v2/v3/v4 的 preparation、code snapshot、live response、append-only ledger、terminal/stop 记录，以及 v3/v4 两份诊断全部永久只读。v5 使用独立 spec、code snapshot、preparation、lock、receipt 和 live root；任何 v5 provider 响应前必须完成结果前 seal。

scientific prereg、冻结 parser hash、128 个 slot、44/42/42、12-cell、每个 length×language 中 4 conflict×4 edit×2、R1 exact/template/5-gram、跨 R2 near-duplicate、固定 128-family/256-candidate 分母、estimand、编码器角色和全部 measurement/Gate 门槛均不变。

v4 的 `accepted_proposals_not_truth.jsonl` 恰有一行 R2SRC-001。v5 seal 与 runner 必须逐字节复验其文件 hash，并验证：

- slot identity 与冻结 registry 的 R2SRC-001 一致；
- v4 R/E/C 三个 attempt-scoped stage lock 的原字符串逐字段装配为该 accepted row；
- v4 complete assembly status、assembly object 和 proposal hash 与 accepted row 一致；
- 未修改 parser、R1 exclusion 与全部机械门禁重算通过；
- `source_attempt_version=source-recovery-v4-attempt-0001` 原样保留。

通过后，R2SRC-001 作为 v5 的 immutable inherited predecessor 导入；v5 不发送任何 R2SRC-001 provider 请求，不替换其正文，并让 R2SRC-002…128 的跨槽 exclusion 看见它。R2SRC-002 的 R lock 只属于已终止的 v4 orchestration attempt，不继承；v5 从 R2SRC-002 的全新 R→E→C attempt 开始。

## 2. 固定 sampling 与 substantive retry

所有 v5 请求固定：`deepseek-v4-flash`、non-thinking、JSON mode、stream=false、`temperature=0.6`、`top_p=0.9`、`max_tokens=4000`。模型和 sampling 参数不得按 attempt、slot 或输出改变。

每个 stage response attempt 的 provider payload 必须包含：

- 独立数值 `stage_response_attempt`；
- 当前数值 `orchestration_attempt`；
- 上一响应的机械 `category`、枚举 `detail` 和必要数值 metrics；不得包含上一失败正文或其片段/hash 以外的内容；
- 从本规范冻结表按 stage、edit level、attempt index 和 failure enum 机械确定的 recovery directive。

每个 stage 的 scheduled strategy 使用有限序列并按 attempt 循环，不根据文本偏好选择：

| stage | 固定策略序列 |
| --- | --- |
| R | interior-length direct；explicit unit self-count；two-clause structured fact；compact exact-schema restatement |
| E level 1 | one local synonym；one local clause-order swap；function-word+synonym pair；local active/passive rewrite |
| E level 2 | phrase synonym rewrite；local clause reorder；subject-frame rewrite；two phrase substitutions |
| E level 3 | full clause reorder；split one clause；merge adjacent clauses；predicate-frame rewrite |
| E level 4 | multi-clause lexical rewrite；split+reorder；merge+predicate rewrite；global syntax rewrite with all facts fixed |
| C level 1–4 | 使用同级表面策略，但始终只改变冻结 conflict_type 的唯一事实槽；其他事实不变 |

failure-specific action 也固定：JSON/schema→exact keys only；language→只用冻结语言；length→按冻结单位对 interior target 自计数；copy/uniqueness→输出前强制执行 scheduled surface operation；edit below/above band→按保存的 ratio 与 changed-character interval 增加/减少非事实编辑；R1/跨槽排除→重新发明本 slot 的虚构实体/表面结构。只传 enum 和数值，不传失败正文。

E/C 只接收当前 orchestration attempt 内构造所必需的 DeepSeek-generated reference；E 可接收 query 用于唯一性门禁，C 可接收 query/equivalent 只用于四字段唯一性提示。禁止发送 R1、Blind、Gate、生产/内部正文、模型分数或人工结果。程序不得改写、扩写、截断、翻译或修补模型字符串。

## 3. 锁、排除与接受

R/E/C 首个 stage 机械合格值仍只锁在当前 orchestration attempt。完整对象必须重新通过未修改 parser、R1 与 inherited/current accepted R2 跨槽 exact/template/5-gram、四文本 normalized 唯一、长度和 edit bands。完整对象失败时 append-only 保留整次 attempt，同 slot 开新 attempt；不得复用其 stage lock。

每 slot 第一个完整机械合格对象是唯一永久接受值；不得继续请求第二个合格对象、不得按措辞/E5/人工/construction role 择优。达到 inherited 1 + newly accepted 127 = 128 后才统一运行 frozen data/exclusion/quota validation 并形成 formal source data lock。

## 4. breaker 与 crash-consistent audit

- identical-response counter key 固定为 `(slot_id, stage, orchestration_attempt, response_sha256)`，阈值 6。
- 同一 slot、同一 stage、当前 orchestration attempt 累计 24 个完整响应未锁定该 stage，fail-closed。
- 同一 slot 连续 24 个完整 assembly attempts 无永久接受，fail-closed。
- 连续 8 次 transport/429/5xx、永久 provider、安全或封存漂移立即停止。

每次 provider 返回后必须依次：response archive+fsync；机械判定；`CALL_COMPLETED` audit+fsync（含 response hash、usage、mechanical outcome）；若 breaker 触发，再写 `HARD_BLOCK` audit+fsync，最后 raise。transport 和 assembly hard block 也必须先记录明确 terminal state。命令 crash/stop 不自动重跑。

usage 中的 provider cache hit/miss 原样记录；没有直接证据时不得宣称 identical output 由 cache 导致。费用/token 不作停止条件。

## 5. 成功后的固定顺序

formal source data lock PASS 后才允许单次本地 E5/DistilUSE；随后生成物理隔离的 relation A/B 与 similarity A/B 盲包。两名研究员每人 relation 256 + similarity 256 = 512 行，到此停止等待真人提交。

人工提交前禁止 finalizer/readiness/Gate A/B；Blind、Reranker、D1–D3、A0/M1 继续禁止。不得 commit/push。
