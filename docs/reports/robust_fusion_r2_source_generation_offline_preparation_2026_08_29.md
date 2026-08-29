# Robust Fusion R2 DeepSeek 正文来源离线准备报告

> research_id: `ROBUST-FUSION-R2-2026-08-29`  
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-GENERATION-2026-08-29-v1`  
> 状态：`AWAITING_EXPLICIT_PAID_API_AUTHORIZATION`  
> 本报告不构成付费调用授权、R2 measurement PASS、readiness 或 Gate A/B 授权。

## 1. 结论

DeepSeek 正文来源的结果前离线实现、代码快照、128-slot registry、价格快照、授权回执模板、封存链与零网络 dry-run 已完成。封存和 dry-run 均发生在任何 R2 正文、E5/DistilUSE 分数或人工结果之前；`network_calls=0`、`api_key_read=false`，未创建 live source-generation run。

现有 R2 prereg manifest 仍为 `b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b`，本次没有修订其 estimand、门槛、样本量或停止规则。R1/Blind/生产数据、模型分数与人工评分均不进入请求体；未来模型输出只标为待独立人工复核的提案，不是真值。

## 2. 固定 frame 与恢复规则

- 128 个 family slot；每 slot 固定 equivalent/conflict 两项，候选固定分母 256。
- dataset 配额为 `public_general/public_domain/internal_control=44/42/42`。
- 12 个 dataset×length×language cell 各 10–11；`short_zh/long_zh/short_en/long_en` 各 32。
- 每个 length×language 聚合内，四类 conflict×四级 edit 的 16 个组合各固定两个 family。
- 每 slot 最多三个版本：`primary-v1`、`recovery-v1-2`、`recovery-v1-3`；仅 transport、JSON/schema、语言/长度/表面区间、R1 exact/template/5-gram near-duplicate 等机械失败可恢复。
- 首个机械合格提案立即接受；不得按措辞偏好、编码器分数或人工结果替换。三次失败即 terminal，固定 slot 记 missing，不得第四次调用或另换样本。

## 3. 调用身份、费用与审计

未来若另获明确授权，调用身份固定为项目现有 `EVAL_JUDGE_BASE_URL=https://api.deepseek.com/chat/completions` 与 `EVAL_JUDGE_MODEL=deepseek-v4-flash`，使用 non-thinking 与 JSON mode。官方 2026-08-17 起 peak 价快照为 cache-miss input `$0.44/1M`、output `$1.32/1M`；预算不采用 cache-hit/off-peak 折扣。

本地上限为每次 input 8,000、output 4,000 tokens，最多 384 次，理论 peak 最大 `$3.3792`；硬熔断 `$5.00`。每次发送前先写 request/slot/model/价格事件，返回后再写 usage、按 peak 价计费、状态与响应 hash，并逐条 flush + fsync。usage 缺失、token 越界、重复 request、既有 live root 或任一封存漂移均 fail-closed。

价格来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

## 4. 封存证据

主目录：`runs/robust_fusion/r2_source_generation_preparation_v1/robust-fusion-r2-source-generation-preparation-v1-20260829/`

| 制品 | SHA-256 |
| --- | --- |
| `manifest.json` | `9de5e8f29b76610a013cc6cdd085d65c22a588ea56bfa20040bee624c856f2db` |
| `lock.json` | `723a4b784676795c84925483ebb0262ead0e047e3ca4cd47d37774fe28110d1c` |
| `slot_registry.jsonl` | `c717641388cf0264ff75b17bec4d4b986a32a309fc6dfe8ab7b13ccbafc29f37` |
| `authorization_receipt_template.json` | `580faf763052a143bc702d333bc82eae24d715578941befd3532a3928274fa85` |
| `dry_run_receipt.json` | `fcb89f25ceb3e5643c0f4141de24b3179c26c749aa753e2a821a3cf1412130c2` |
| `dry_run_lock.json` | `5dafb5ec6894a2a3c03c5cbd9a088521d6bc125a36bd06a23ba17c1924948d05` |
| implementation spec | `8879814e27bacc4ab54b7a5879358a01227bb084e0c61a2a669c91df06fbb02c` |
| price snapshot | `66374b07a8f2d4fd7973dcd65c533acd82256c0b51de2d328f296b591fb4d705` |

代码快照位于上述目录的 `code_snapshot/`，同时 manifest 绑定工作区原文件与快照。dry-run 构造了 384 个唯一请求信封，其计划 hash 为 `cb55778dd0c9884ec796b1398a7d4a3488c0a0a972b543954c77a55a7425c3a5`。

复算命令：

```bash
PYTHONPATH=src:. .venv/bin/python scripts/prepare_robust_fusion_r2_source_generation.py verify
```

`dry-run` 是 append-only 的一次性动作，已有 receipt 时拒绝重放。

## 5. 校验结果

- 目标 Ruff：通过。
- source-generation 目标单测：10 passed。
- 全量非集成测试：456 passed、3 deselected。
- import-lint：174 files、829 dependencies、0 broken。
- report index check、`git diff --check`、封存 `verify`：通过。
- 重复 dry-run：按预期拒绝，错误为 `dry-run receipt exists; refusing replay`。
- 用未填写模板尝试 live 入口：在读取 provider key 和创建 live root 前按预期拒绝；live root 不存在。

全仓无路径限制的 Ruff 仍报告 237 个既有历史告警，主要来自旧脚本执行位、导入顺序与旧源码规则；本任务未修改这些无关文件，也不把它们计作本任务目标 Ruff 通过。封存覆盖的四个 source-generation 代码/测试文件单独 Ruff 为全绿。

## 6. 唯一下一动作

研究负责人若决定承担最多 `$5.00` 的 DeepSeek 付费调用，应从封存的 `authorization_receipt_template.json` 复制到一个新的、独立回执文件，填写 `authorization_id`、`authorized_by`、`authorized_at`，不得修改模板或 preparation 目录。授权后才可由本任务执行：

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_robust_fusion_r2_source_generation.py execute \
  --authorization-receipt /absolute/path/to/completed-authorization-receipt.json \
  --allow-paid-api
```

当前不得执行该命令。后续即使 source proposals 完成，仍须先锁正文与固定分母，再单次 E5/DistilUSE、两名研究员各 512 行、先锁后验/必要仲裁及一次性 measurement finalizer；只有 measurement 全 PASS 才可进入 readiness。
