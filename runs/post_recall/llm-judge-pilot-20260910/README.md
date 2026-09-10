# N09：LLM judge pilot（2026-09-10）

## 实际结果索引（负责人侧运行，2026-09-10）

正式报告见 [docs/reports/llm_judge_pilot_2026_09_10.md](../../../docs/reports/llm_judge_pilot_2026_09_10.md)。下方各节是工程会话的实现说明；本节列出真实运行的产物目录。

| 级别 | 判断目录 | 评价／训练目录 | 要点 |
| --- | --- | --- | --- |
| L1 开发 | `l1-development-judge/`（low）、`l1-development-judge-medium/` | `l1-development-eval/`、`l1-development-eval-medium/` | 官方 55/74，人审 52/52 |
| L1 确认 | `l1-confirmation-judge/`（low）、`l1-confirmation-judge-medium/` | `l1-confirmation-eval/`、`l1-confirmation-eval-medium/` | 官方 270/371，双向 114/185 |
| 第一阶段分数与条目 | `items-stage1-top20/{development,confirmation,train}/` | — | `baseline_score` 前 20；`_engineering-checks/stage1-verification-v2/` 为代码复算一致性验证 |
| L2 开发 | `l2s-development-judge/` | `l2s-development-k10-v2/`、`l2s-development-k20-v2/` | K=20：62 到 64/74 |
| L2 确认 | `l2s-confirmation-judge/` | `l2s-confirmation-k10-v2/`、`l2s-confirmation-k20-v2/` | K=20：311 到 312/371 |
| L3 | `l3s-train-judge-8w/`（8 并发；其前身 4 并发运行在 `_superseded/l3s-train-judge/`，缓存已续用） | `l3s-stage1-v2-training/`、`l3s-development-v2-evaluation/`、`l3s-confirmation-v2-evaluation/` | 确认 313/371，`judge_score` 分裂 111 |
| 被替代 | `_superseded/`：`items-development-l2/`、`l2-development-judge/`、`items-train-l3/`、`l3-train-judge/`（E0 前 10 选择，已中止）、`l1-confirmation-judge-resume/`（全缓存命中的重复运行）、`l1-development/`（工程会话内的空结果） | `_superseded/l2-development-eval/` | E0 前 10 覆盖不足，指标与 E0 相同 |
| 冒烟与工程验收 | `smoke-real/`（负责人侧成功）；`_engineering-checks/`：`smoke/`、`smoke-isolated-state/`（工程会话内阻断记录）、`validation/`、`stage1-verification-v2/`、后台运行日志 | — | — |

`baseline/{development,confirmation,train}/` 为英文基线全池分数，开发与保存结果逐值一致。

当前 L2/L3 已统一改为 **固定 hybrid fusion stage 1 → judge**，默认 **K=20**。Stage 1 是英文 `build_online_features` 的 `baseline_score` 列；E0 指英文 LambdaMART，两者不可混用。相同分数按 `chunk_id` 升序生成列表。

经理反馈真实 judge 已可运行，L1 development 官方 55/74（E0 44）、human v5 52/52；L1 confirmation 官方 270/371（E0 208），双向 114/185（E0 40）。这些是本轮交接中的经理报告，本次工程修改没有重新运行或独立复算它们，也不等待后台 judge。

E0 排名无法覆盖指定对：经理诊断的双候选 top-10 覆盖仅 dev 1/74、confirmation 12/371。固定 fusion top-20 为 72/74、355/371。因此旧 **E0-top-10 L2** 及 `l2-development-*` 目录是 **superseded 的历史记录**，其中 44/74 不变的结果保留；代码不再提供 E0-top-K 选择路径。原 [task-spec.md](task-spec.md) 的 L2/L3 选择定义已由经理本轮要求替代，L1 提示和数据边界保持。

## 当前实现与评价口径

- `stage1-scores --role --out`：从已保存候选重算英文特征，提取 `baseline_score`，按候选顺序输出 `stage1-{role}.jsonl`。Development 必须与 `items-stage1-top20/development/stage1-development.jsonl` 逐值逐序一致。
- `items --level l2|l3 --stage1 <分数> --top-k 20 --out <新目录>`：仅按 stage 1 选择，输出 `{role}.jsonl`。Development 的 `(query, chunk)` 集合必须与经理 scratch 一致；较小 K 检查同一 scratch 的前 K 子集。L1 继续使用 `--baseline` 和指定候选。
- `evaluate-l2`：同时报告 `E0`、`stage1`、`stage1_judge`、`E0_judge`。两个 judge 排序器只重排 stage-1 top-K，次级分数分别为 stage 1、E0；余下候选都保持 stage-1 顺序。已判 top-20 可用于 K=10，只使用 top-10 分数。任一范围内候选 unavailable 时，该查询整体回退 stage 1；范围外的 unavailable 不触发回退。
- 四个排序器均有官方严格成对指标，development 另有 human v5 52 题指标；均有相对 E0 和 stage1 的 corrected/damaged 四格及来源组明细。列表指标为共同覆盖查询上的 `preferred@1`、`preferred@3`、`preferred_mrr`、`mean_rank_preferred`、`mean_rank_other`。Human 列表指标使用其可评价子集和人类偏好方向。
- 成对评价遵循严格数值／排序键同分；`chunk_id` 不把模型同分变成成对正确。列表名次使用确定性 ID 同分顺序，名次从 1 开始。列表命中率和 MRR 为 0–1 数值。重排后 top-K 与剩余部分是两个连续区段，同一区段内相同排序键仍为严格同分。
- Trigger 的 `fallback_queries`、`changed_queries` 及 `by_query` 覆盖所有输入查询，列表／成对指标才使用共同覆盖人群。`judged_calls_per_query` 指本次使用的查询／段落判断数（含缓存，不是远端子进程数）；原 judge 批次、缓存和耗时保留在 `judge_run`。
- L3 使用离线 **`candidate_difference_v3_en_llm_judge_v2`**：English38 + `judge_available` + `judge_score`。只有 stage-1 top-K 可进入新增列，其他候选为 0／NaN；传入更多已判候选时忽略范围外分数。训练／推理均校验 stage1 值确实等于完整特征矩阵的 `baseline_score` 列，旧 E0 选择契约的模型包拒绝加载。
- L3 保留固定 N08 c3、seed 20260907、来源均衡权重和早停；E0 控制拟合后必须精确复现保存 development 分数，才拟合 judge 臂。训练与推理结果均报告 L3 列表指标及 `judge_feature_splits`，来自实际模型 `feature_importance(importance_type="split")` 的两项计数。

模型配置为 `gpt-6-astra`、effort `low`、`codex-cli 0.153.4`，提示 `judge_prompt_v1` 未改。保留经理三项修改：unavailable 缓存可在后续运行重试；过长 reason 不再使批次失败；移除 judge 的 development-only gate。本工程会话没有运行 judge、训练真实模型或读取官方 Test。

## 本轮实跑验证

在新目录 `stage1-verification-v2/` 中执行 development 本地重算：**76 查询、10,465 分数及顺序与 scratch 精确一致**（1.7656 秒），**1,520 个 top-20 item 的 query/chunk 集合与 scratch 一致**。原 scratch、后台 judge 输出及旧结果文件均未改写。

完整非 integration：**1,218 passed、3 deselected、6 warnings，17.05 秒**，包括导入边界；judge 专项 **28 passed**。5 个相关 Python 文件 Ruff 通过，变更 CLI 帮助通过。验收在 [acceptance.json](_engineering-checks/stage1-verification-v2/validation/acceptance.json)，文件与未验证项见 [implementation-notes-v2.md](implementation-notes-v2.md)。真实 L2/L3 新设计指标、真实训练树分裂计数及 confirmation/train scratch 重算未在本轮验证。

## 经理可运行的命令

从仓库根目录运行，等待对应 judge 的 `scores.jsonl` 和 `summary.json` 完整后再使用。以下每个输出目录必须尚不存在；不覆盖旧结果。

```bash
pilot_run=runs/post_recall/llm-judge-pilot-20260910
stage1_root="$pilot_run/items-stage1-top20"

# Four L2 evaluations: development/confirmation, K=10/20 from the same judged top 20.
for pilot_role in development confirmation; do
  for pilot_k in 10 20; do
    .venv/bin/python scripts/llm_judge_pilot.py evaluate-l2 \
      --role "$pilot_role" \
      --baseline "$pilot_run/baseline/$pilot_role/scores.jsonl" \
      --stage1 "$stage1_root/$pilot_role/stage1-$pilot_role.jsonl" \
      --scores "$pilot_run/l2s-$pilot_role-judge/scores.jsonl" \
      --top-k "$pilot_k" \
      --out "$pilot_run/l2s-$pilot_role-k$pilot_k-v2"
  done
done

# Fixed c3 E0 control + stage1-top20 judge feature arm.
.venv/bin/python scripts/llm_judge_pilot.py train-l3 \
  --config runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json \
  --train-baseline "$pilot_run/baseline/train/scores.jsonl" \
  --dev-baseline "$pilot_run/baseline/development/scores.jsonl" \
  --train-stage1 "$stage1_root/train/stage1-train.jsonl" \
  --dev-stage1 "$stage1_root/development/stage1-development.jsonl" \
  --train-scores "$pilot_run/l3s-train-judge/scores.jsonl" \
  --dev-scores "$pilot_run/l2s-development-judge/scores.jsonl" \
  --model gpt-6-astra --effort low --top-k 20 \
  --out "$pilot_run/l3s-stage1-v2-training"

# Reload the trained bundle and evaluate each role; K comes from the model contract.
for pilot_role in development confirmation; do
  .venv/bin/python scripts/llm_judge_pilot.py evaluate-l3 \
    --role "$pilot_role" \
    --baseline "$pilot_run/baseline/$pilot_role/scores.jsonl" \
    --stage1 "$stage1_root/$pilot_role/stage1-$pilot_role.jsonl" \
    --scores "$pilot_run/l2s-$pilot_role-judge/scores.jsonl" \
    --bundle "$pilot_run/l3s-stage1-v2-training/judge-model" \
    --out "$pilot_run/l3s-$pilot_role-v2-evaluation"
done
```

这些命令没有在本工程会话运行。L3 训练的 `results.json` 已含 development 评价；单独 `evaluate-l3 development` 用于经理选择的导出／加载复核。Confirmation 按一次冻结模型评价使用。

## 保留的首轮历史

初版受本执行环境的 Codex app-server 初始化权限错误阻断，两次不同三项 smoke 共 8 次子进程、36.5665 秒，没有有效判断；经理之后已在自己的 shell 跑通。原 `smoke/`、`smoke-isolated-state/`、`l1-development/results.json` 的阻断状态及 [implementation-notes.md](implementation-notes.md) 原样保留，只描述首轮事实，不代表最新真实结果或当前缓存政策。首轮 E0 的官方 44/74、human v5 31/52 和全池精确重放仍是已核验的历史事实。

## N10 追加（2026-09-10）：开源判断器对照

`l1-development-judge-qwen3-8b{,-think}`、`l1-development-judge-qwen3-14b-awq{,-think}` 及对应 `l1-development-eval-*`、`l1-development-agreement-*-vs-gpt6*.json`：同一 L1 开发 148 项，vLLM 0.29 / RTX 4090。`-smoke` 目录为 3 项冒烟。结果见[报告 §10](../../../docs/reports/llm_judge_pilot_2026_09_10.md#10-开源判断器对照n10)。
