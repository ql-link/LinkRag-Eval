# 交接说明：issue #23 与 #24 的前置产物（2026-09-10）

本文给接手 #23（列表塌陷受控证据）与 #24（跨分布小探针）的成员。前置工作已在分支 `feat/open-judge-runner` 完成并合入 `master`；接手人从 `master` 切自己的 `feat/<slug>` 分支即可。术语与总计划见[并行研究计划](parallel-research-plan-2026-09-10.md)，基线数字见[N09/N10 报告](../reports/llm_judge_pilot_2026_09_10.md)。

## 0. 先要拿到的东西

| 项 | 位置 | 由谁给 |
| --- | --- | --- |
| 代码与文档 | `master`（含 `scripts/llm_judge_pilot.py`、`llm_judge_local.py`、探针集 `fixture.json`、`review-sheet.md`、各 README） | Git |
| 被忽略的运行产物包 | `runs/post_recall/_handover/handover-23-24-20260910.tar.gz`（17 MB，负责人本机）；在仓库根目录 `tar -xzf` 到 `runs/post_recall/` 即可还原 | 负责人私下共享 |
| 4090 判断器服务器 | `ssh runpod`（需负责人分发 SSH 公钥）；`/workspace/serve_qwen3_14b.sh` 启动 Qwen3-14B-AWQ，`/workspace/serve_qwen3.sh` 启动 Qwen3-8B；本机 `ssh -f -N -L 8000:127.0.0.1:8000 runpod` 后访问 `http://127.0.0.1:8000` | 负责人 |
| GPT-6 判断（可选对照） | 本机 `codex` CLI 订阅；`--runner codex` | 各自订阅 |

产物包内容：`list-collapse-inputs-20260910/`（#23 全部输入）、`llm-judge-pilot-20260910/{README.md,baseline,items,items-stage1-top20/{development,confirmation},l1-*}`、`ood-probe-20260910/`（含 GPT-6 与 Qwen3-14B-AWQ 的判断输出）。不含 L2/L3 与 Train 判断（#23/#24 用不到）。

## 1. #23：列表塌陷

**已完成（第一部分的输入）**：`runs/post_recall/list-collapse-inputs-20260910/`，四个排序器在确认集 371 题全池的分数，统一格式 `{"source_query_id", "scores": [{"chunk_id","score"}]}`；`confirmation-list-metrics-reference.json` 是参考值（首选段@1／@3、MRR、两段平均排名），正式报告需重算。读法见该目录 README。

**待做**：
1. 第一部分：新建 `runs/post_recall/list-collapse-<日期>/`，用 `linkrag_eval.retrieval.learning_to_rank.llm_judge.list_metrics` 与 `score_maps` 对 A／B／E0／融合重算列表指标，核对与参考值一致，写短报告 `docs/reports/list_collapse_<日期>.md`。
2. 第二部分（可选）：在 `pairwise_training.py` 加"背景负例采样"开关（默认关），按 N08 c3 配置重训一次，比较成对指标与列表指标。配置文件路径见 issue 正文。

**边界**：只读上述输入；`pairwise_training.py` 是本 issue 独占。

## 2. #24：跨分布小探针

**已完成**：
- 探针集 `runs/post_recall/ood-probe-20260910/fixture.json`（`ood_probe_v1`）：英文 6 查询×8 文档原样引用，中文 12 对最小编辑对，共 96 条判断条目 `items.jsonl`。
- 转换与评估：`scripts/llm_judge_pilot.py probe-items` / `probe-evaluate`。
- 判断输出：GPT-6 low（30/30 方向全对）、Qwen3-14B-AWQ 不思考（中文 16/24）与思考（14/24），结果登记在目录 README 与报告 §10.2。
- 复核表 `review-sheet.md` 与复核方法（README「复核方法」）。

**待做**：
1. 中文标签第二人复核，填 `assessment.reviewed_by` 后冻结（复核前的 Qwen 结果只能算试跑）。
2. 复核后按需重跑（命令如下），把"初步迹象"一段写进报告；样本量小，措辞不得外推。
3. 若要加第二个开源模型（如 Qwen3-8B 思考），换 `--model` 与服务器脚本即可，不改提示词。

```bash
P=runs/post_recall/ood-probe-20260910
.venv/bin/python scripts/llm_judge_pilot.py judge --runner openai --endpoint http://127.0.0.1:8000 \
  --model qwen3-14b-awq --items $P/items.jsonl --out $P/judge-<tag> --workers 8 [--think]
.venv/bin/python scripts/llm_judge_pilot.py probe-evaluate --items $P/items.jsonl \
  --scores $P/judge-<tag>/scores.jsonl --output $P/evaluation-<tag>.json
```

## 3. 共同约束

- 判断器提示词 `judge_prompt_v1` 不改；改动需另开 issue。
- 输出目录不覆盖：所有子命令遇到已存在的输出会拒绝，换新 tag。
- 缓存：`judge` 会读取 `runs/post_recall/llm-judge-pilot-20260910/**/judge-cache`，键含模型名与 effort（`none`／`think`／`low`），不同模型不会串用。
- 思考模式默认 `max_tokens` 4096，约 2% 条目会截断成 `unavailable`；重跑同一命令只补跑这些条目。
- 不读官方 Test 逐题。
