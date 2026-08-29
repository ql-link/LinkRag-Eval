# Robust Fusion R2 DeepSeek 正文来源执行规范 v2

> research_id: `ROBUST-FUSION-R2-2026-08-29`  
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-EXECUTION-2026-08-29-v2`  
> 状态：`AUTHORIZED_RESULT_BEFORE_READY_TO_SEAL`  
> 本规范追加于 v1，不覆盖 v1，也不修改正式 R2 scientific prereg。

## 1. 修订依据与边界

研究负责人通过用户明确授权“不设定费用上限，不要担心token费用，使用到达到目标即可”。正式 R2 scientific prereg 只冻结 128-family、固定 strata/分母、正文先锁、单次编码和一次性 measurement；没有规定 source API 每槽三次、384 次或 `$5` 熔断。因此 v1 中这些限制属于 source-preparation 执行约束，可由本 v2 透明 supersede；R2 estimand、门槛、样本量、family identity 和确认性边界不变。

v1 preparation manifest `9de5e8f29b76610a013cc6cdd085d65c22a588ea56bfa20040bee624c856f2db`、lock `723a4b784676795c84925483ebb0262ead0e047e3ca4cd47d37774fe28110d1c`、dry-run lock `5dafb5ec6894a2a3c03c5cbd9a088521d6bc125a36bd06a23ba17c1924948d05` 和全部代码快照永久保留。v2 只 supersede：每槽三次、384-call 总上限、input/output token 预算门禁和 `$5` 熔断。

## 2. 不变科学设计

- 原 128 个 slot、44/42/42 dataset 配额、12 cell、四类 conflict×四级 edit×每格两个 family 全部不变；不得增样、换槽或删除。
- 每 slot 仍只接受首个机械合格输出；模型分数、人工结果、措辞偏好、construction role 或希望改善某 cell 均不得触发替换。
- 只发送全新非敏感 synthetic microfact schema、slot strata 和机械约束；禁止发送 R1、Blind、Gate、生产/内部正文、检索结果、编码器分数、人工评分或密钥。
- 模型输出永远标为 `PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW`，不能成为 relation 或 similarity 真值。

## 3. 调用与恢复状态机

调用固定项目当前 `EVAL_JUDGE_BASE_URL=https://api.deepseek.com/chat/completions`、`EVAL_JUDGE_MODEL=deepseek-v4-flash`，`thinking={"type":"disabled"}`、JSON mode、stream false。`max_tokens=4000` 是单响应传输参数，不是研究总 token 预算。

attempt 按 `source-execution-v2-attempt-0001...` 无总次数上限地版本化。只有 transport/timeout、429/5xx、JSON parse、exact schema、语言/长度/编辑距离或 R1/slot 间 exact/template/5-gram near-duplicate 等机械失败允许继续同 slot；首个机械合格响应立即锁定并进入下一 slot。

以下是非费用型硬阻塞，立即停止整个命令并保留现场：

- 400/401/403/404 等永久 provider 错误、响应 usage/envelope 漂移或安全边界违例；
- 同一 slot 连续 8 次 transport/429/5xx 失败；
- 同一 slot 连续 24 次同一机械失败类别，或同一响应 hash 重复 6 次，视为不可恢复循环；
- sealed manifest、authorization、slot identity、R1 exclusion、append-only ledger 或固定分母完整性漂移。

这些 circuit breakers 不是费用或 token 上限。若命令级 crash/硬阻塞，不得静默重跑；只报告 exit/error、已完成 slot 与账本，等待版本化恢复安排。

## 4. 审计、成本与数据锁

每次调用发送前将 slot、attempt、request hash、model 与授权/价格快照写入 append-only JSONL 并 flush+fsync；返回后追加 usage、实际 peak 估算成本、response hash 和机械判定。所有原始 synthetic response 另写 append-only archive，失败不删除。仍按 v1 官方 peak price snapshot 计算并累计 input cache-hit/cache-miss/output 成本，但不作停止条件。

达到 128/128 后，机械转换为正式 family schema，再无条件运行冻结 `validate_family_frame`：R1 exact/template/5-gram exclusion、slot 间 near-duplicate、44/42/42、12-cell、4×4×2、128 family/256 candidate 固定分母必须全 PASS。通过才写 append-only data lock；任何失败 terminal，禁止编码器。

## 5. 后续边界

数据锁 PASS 后才允许单次运行冻结 E5/DistilUSE，再生成物理隔离的 relation A/B 与 similarity A/B 包。两名研究员各需 relation 256 + similarity 256 = 512 行。人工结果回来前不得 finalizer/readiness/Gate；Blind、Gate A/B、Reranker、D1–D3、A0/M1 继续禁止。不得 commit/push。
