# Robust Fusion R2 结果前预注册、排除注册表与旧 inventory 资格审计

## 结论

`ROBUST-FUSION-R2-2026-08-29` 已完成本地结果前 protocol/measurement seal、有效功效模拟 v2、R1 hard-exclusion registry 和 outcome-blind 旧 Gate inventory 元数据审计。当前状态为 `PREREGISTERED_AWAITING_AUTHORIZED_R2_TEXT_SOURCE`：尚未生成任何 R2 候选正文、未运行 E5/DistilUSE、未发人工包、未读取 Blind、未运行 readiness 或 Gate A/B。

## 功效与实现纠错

功效模拟 v1 在正式 prereg seal 前被单测发现 frame allocation bug：conflict type 与 edit level 被同一模运算耦合，未实现每个 length×language 内 4×4×2 的正交分配。v1 文件和结果原样保留，并以 `invalidation_notice.json`（SHA-256 `4bd23a8d426047594ecdcd01d35554acb4cf1ff91b1effcd9ba01de976752d69`）标记 `INVALID_FOR_PREREGISTRATION`；没有覆盖或改写。

独立 v2 只修正 frame allocation，n=128、12-cell 条件标准化、dataset 等权、门槛、caliper、共同支持层级、随机种子和迭代数均不变。v2 在 ρ=.30/.50/.60/.65 的完整门禁通过率分别为 0%/52.5%/91.25%/92.75%；规划替代值 .60 的 Monte Carlo SE 为 1.41%。结果 SHA-256 为 `8a44cc483c7a981085d42f50016f9d545d35023afcd1e7a46cbbb411dfed9c48`，manifest SHA-256 为 `4cb1629f996923a7f493be9646c916f86137bda894202cb10c18f8a93b7c39b2`。

## 正式 seal

正式协议为 [R2 research](../plans/robust-fusion-r2-research.md) 与 [R2 similarity measurement](../plans/robust-fusion-r2-similarity-measurement.md)。本地 seal 发生在任何 R2 正文、编码器分数或人工结果之前；不声称外部时间戳。

| 制品 | SHA-256 |
| --- | --- |
| `preregistration/manifest.json` | `b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b` |
| `preregistration/lock.json` | `bfbb68d5615e18053b76b14ddf6f1fd0fad92d4e888c06b998fbed2ab854ff37` |
| `preregistration/receipt.json` | `b10d7c63263116df6ee9f697abed7add745826e514cef27b95ae0439d7cafc9f` |

seal 哈希固定正式协议、功效代码、family frame/near-duplicate 验证、候选—Clean 参照最大余弦、双盲包、A/B 一致性与一次性 finalizer 实现。每位研究员固定 relation 256 + similarity 256 = 512 行。

## R1 排除与旧 inventory 审计

R1 registry SHA-256 为 `f54115330edeabb077d149f09106051a210fb086669208dd5177839989c4fe16`，包含 212 个 family-key hash、508 个文本 hash、174 个模板 hash 和 428 个近重复 5-gram 集；阈值固定为规范化字符 5-gram Jaccard `>=0.82` 拒绝。输入覆盖 R1 v1、唯一 supplement、Internal v6 route v5 的 query/chunk/family 元数据；历史 Blind v4/v5 永久排除。

旧 inventory 审计 SHA-256 为 `779bb50d2c3abc9a91f2293ee03432d0828b038b69b967a1c66814b160f35ab0`。审计没有解析三个旧 preflight JSON，只记录文件身份、字节数与 SHA-256；没有读取确认性排序结果。因不存在独立 allowlist 的 family/provenance/strata inventory，结论为 `NOT_ELIGIBLE_METADATA_INSUFFICIENT`。这既不授权 Gate，也不声称旧 cohort 已失去未见状态。

## 当前阻塞与唯一下一动作

仓库内没有现成的完整 128-family 集合能够同时证明：全新 family-disjoint、三 calibration source role 配额 44/42/42、12 个 length×language×dataset cell、四类冲突×四级编辑正交，以及双语正文质量。用当前 Codex 会话直接撰写也属于模型生成正文。因此下一步需要研究负责人提供一种获授权的正文来源：人工团队按冻结 schema 编写，或批准指定外部生成服务/API 及预算。收到正文后只能先做排除/配额验证并锁定固定分母，再单次运行本地编码器；不能按分数替换。
