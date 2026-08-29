# Robust Fusion R2 DeepSeek 正文来源实现规范 v1

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-GENERATION-2026-08-29-v1`
> 状态：`RESULT_BEFORE_IMPLEMENTATION_SPEC_FINAL_FOR_SEAL`
> 本规范位于既有 R2 prereg 之外，不修改其 estimand、样本量、配额、门槛或停止规则。

## 1. 调用身份与数据边界

未来仅在研究负责人再次明确授权付费调用后，使用项目 `.env.eval` 的 `EVAL_JUDGE_BASE_URL=https://api.deepseek.com/chat/completions`、`EVAL_JUDGE_MODEL=deepseek-v4-flash` 与本地密钥。请求固定 OpenAI Chat Completions JSON：`thinking={"type":"disabled"}`、`response_format={"type":"json_object"}`、`stream=false`、`temperature=0.2`、`max_tokens=4000`。

每次请求只包含一个全新 slot 的 synthetic microfact schema、dataset role、language、length、conflict type、edit level 与结构约束。绝不发送 R1 正文/ID、Blind、Gate、生产数据、检索结果、编码器分数、人工评分、分带或 API 密钥。模型输出只是待后续双人 relation/similarity 复核的构造提案，不是真值；`construction_role` 永远不能代替人工 relation。

## 2. 固定 128-slot frame

slot 从有效功效模拟 v2 的正式 frame 机械派生：dataset role 配额 `public_general/public_domain/internal_control=44/42/42`；12 个 dataset×length×language cell 各 10–11 family；四个 length×language 聚合各 32 family；每聚合严格为四类 conflict（numeric、version_time、negation_direction、applicability_condition）×四级 edit×每格两个 family。每 slot 固定一个 equivalent 与一个 factual-conflict 提案，固定候选分母 256。不得增加、删除、换 slot 或按内容偏好重分配。

四级 edit 只作结果前词面/句法控制：1=局部词面替换；2=短语级复述；3=句法重排；4=多处局部复述。机械 normalized-Levenshtein 仅验证预设表面区间，不判断语义正确性。

## 3. 恢复与唯一停止

每 slot 最多三个版本化 attempt：`primary-v1`、`recovery-v1-2`、`recovery-v1-3`。只有 transport、JSON parse、exact schema、长度/语言/表面结构、R1 exact/template/5-gram near-duplicate 等机械失败允许进入下一个 attempt。首个机械合格输出立即锁定；不得因为措辞风格、E5/DistilUSE、人工评分或希望改善某 cell 而重试。三次均失败时 source generation 立即 terminal，slot 保留为 missing，禁止替换或开启第四次。

每次 attempt 在发送前把 request hash、prompt version、slot、模型与价格快照写入 append-only ledger，并在返回后追加 HTTP/parse/validation 状态、输入/输出 token、按 peak 价计算的美元成本与响应 hash；每条记录写后 flush + fsync，进程中断也不得抹去已发请求。已存在 run root、已锁 slot 或重复 request hash一律拒绝。正式 128-family 固定分母只有在所有 slot 首个合格提案均完成并通过全局 R1/slot 间排除后才能锁定；否则不得运行编码器。

## 4. 价格与硬熔断

官方价格快照取自 [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)；2026-08-17 起 `deepseek-v4-flash` peak 为每百万 token：cache hit input `$0.014`、cache miss input `$0.44`、output `$1.32`。预算永远按更贵的 peak cache-miss input + peak output 计算，不使用 off-peak/cache-hit 折扣。

每调用本地保守上限为 input 8,000 tokens、output 4,000 tokens，最大 384 次，理论最坏成本 `$3.3792`。硬熔断固定 `$5.00`：每次发送前必须确认累计已记成本加该调用最坏保留额 `<=$5.00`；响应后按 usage 重算，达到或超过 `$5.00` 立即停止。usage 缺失、超 token 上限或价格快照/hash 不一致均停止，不能猜测。

## 5. 授权与禁止

离线 `seal`、`verify`、`dry-run` 必须保持 `network_calls=0`，不读取 API key。`seal` 保存代码快照、输入 hash manifest、authorization receipt 空白模板与 lock；`dry-run` 另存 receipt 与 lock，且两者存在并通过链式校验才允许未来 live runner 继续。未来 live 命令必须同时提供由批准人填写的独立 authorization receipt、receipt 中匹配 source protocol/price/implementation hashes，并显式传入 `--allow-paid-api`；模板占位符未替换、缺少 dry-run lock 或任一 hash 漂移均拒绝。缺一即拒绝。当前状态必须停在 `AWAITING_EXPLICIT_PAID_API_AUTHORIZATION`。

本阶段及正文生成阶段都禁止运行 E5/DistilUSE、人工包、readiness、Gate A/B、Reranker 效果、D1–D3、A0 或 M1。不得修改已封存 R2 prereg，不得 commit/push。
