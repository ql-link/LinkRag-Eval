# 交接说明：issue #23 与 #24 的前置产物（2026-09-10）

本文给接手 #23（列表塌陷受控证据）与 #24（跨分布小探针）的成员。前置代码已在分支 `feat/open-judge-runner` 完成并合入 `master`；接手人从 `master` 切自己的 `feat/<slug>` 分支即可。术语与总计划见 [docs/plans/parallel-research-plan-2026-09-10.md](parallel-research-plan-2026-09-10.md)，基线数字见 [docs/reports/llm_judge_pilot_2026_09_10.md](../reports/llm_judge_pilot_2026_09_10.md)。

> 路径约定：下文展示的项目文件路径均相对于仓库根目录 `LinkRag-Eval/`，所有命令也从该目录执行。Markdown 链接按文档位置解析。2026-09-11 补入 #23 缺失的确认集监督与查询，并同步包内输入说明；压缩包沿用原文件名。

## 0. 先要拿到的东西

| 项 | 位置 | 由谁给 |
| --- | --- | --- |
| 代码与文档 | `master`；运行器入口为 `scripts/llm_judge_pilot.py`，实现位于 `src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py` 与 `src/linkrag_eval/retrieval/learning_to_rank/llm_judge_local.py` | Git |
| 被忽略的运行产物包 | `runs/post_recall/_handover/handover-23-24-20260910.tar.gz`，约 18 MB；包含 #23 第一部分所需输入 | 负责人提供压缩包，接收方放到左列相对路径；clone 不会自动下载 |
| 4090 判断器服务器（仅新增 #24 推理时需要） | `ssh runpod`；复用负责人提供的已启动模型服务。隧道命令：`ssh -f -N -L 8000:127.0.0.1:8000 runpod`，本机端点 `http://127.0.0.1:8000` | 负责人提供 SSH 访问与服务配置；#23 第一部分离线计算无需此服务 |
| GPT-6 判断（可选对照） | 本机 `codex` CLI 订阅；`--runner codex` | 各自订阅 |

接收者取得压缩包后，在自己的仓库根目录执行：

```sh
mkdir -p runs/post_recall
tar -xzf runs/post_recall/_handover/handover-23-24-20260910.tar.gz -C runs/post_recall
```

包内条目以 `runs/post_recall/` 为基准，因此解压必须带上上述 `-C`，不能直接展开到仓库根目录。解压后的项目路径包括：

- `runs/post_recall/list-collapse-inputs-20260910/`：A／B 分数、参考结果及完整输入清单。
- `runs/post_recall/llm-judge-pilot-20260910/`：原包的 baseline、items、开发／确认 stage1 分数与 L1 产物；#23 使用其中的 E0 与固定融合分数。
- `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/confirmation/supervision.jsonl`：本次补入的 374 条官方监督。
- `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/confirmation/queries.jsonl`：本次补入的 374 条英文查询。
- `runs/post_recall/ood-probe-20260910/`：原包的探针集及 GPT-6／Qwen3-14B-AWQ 判断输出。

本次保留原模型产物，不补入训练数据、模型权重或 L2/L3 判断。#24 后续收到的 `runs/post_recall/ood-probe-20260910/review-sheet-completed.md` 与 `runs/post_recall/ood-probe-20260910/review-validation.json` 不在本包内；需要这些补充资料时由负责人另行提供。

## 1. #23：列表塌陷

2026-09-11 成员交付已接入，开发／确认核验与 Test 接收边界见[结果入口](../../runs/post_recall/list-collapse-20260910/README.md)。下述步骤保留为原前置输入交接说明，不表示需要重新训练或重新采集。

**已完成（第一部分的输入）**：四个排序器各有 374 条确认查询的全池分数，每题 100–246 个候选；四份查询与候选 ID 集合相同。3 条查询未同时覆盖两个指定段，主评价保留其余 371 条。评分的公共字段为 `{"source_query_id", "scores": [{"chunk_id","score"}]}`。七份输入的完整项目相对路径、标签字段及筛选口径见 [runs/post_recall/list-collapse-inputs-20260910/README.md](../../runs/post_recall/list-collapse-inputs-20260910/README.md)。

`runs/post_recall/list-collapse-inputs-20260910/confirmation-list-metrics-reference.json` 是已有参考值（首选段@1／@3、MRR、两段平均排名等），正式报告需独立复算。文件位于 `items-stage1-top20` 目录不代表评分只含前 20；本包提供的是完整池分数。

**待做**：
1. 第一部分：新建 `runs/post_recall/list-collapse-<日期>/`，用 `linkrag_eval.retrieval.learning_to_rank.llm_judge.list_metrics` 与 `score_maps` 对 A／B／E0／融合重算列表指标，核对与参考值一致，写短报告 `docs/reports/list_collapse_<日期>.md`。
2. 第二部分（可选）：在 `src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py` 加"背景负例采样"开关（默认关），按 `runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json` 中的 N08 c3 配置重训一次，比较成对指标与列表指标。该配置与 Train／开发训练输入未包含在本包，开展第二部分前另行取得，不从第一部分的确认集评分重建训练数据。

**边界**：第一部分只读上述输入；`src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py` 是本 issue 独占。

## 2. #24：跨分布小探针

**已完成**：
- 探针集 `runs/post_recall/ood-probe-20260910/fixture.json`（`ood_probe_v1`）：英文 6 查询×8 文档原样引用，中文 12 对最小编辑对；判断条目为 `runs/post_recall/ood-probe-20260910/items.jsonl`，共 96 条。
- 转换与评估：`scripts/llm_judge_pilot.py probe-items` / `probe-evaluate`。
- 判断输出：GPT-6 low（30/30 方向全对）、Qwen3-14B-AWQ 不思考（中文 16/24）与思考（14/24），结果登记在 `runs/post_recall/ood-probe-20260910/README.md` 与 `docs/reports/llm_judge_pilot_2026_09_10.md` §10.2。
- 复核表 `runs/post_recall/ood-probe-20260910/review-sheet.md`；复核方法在 `runs/post_recall/ood-probe-20260910/README.md`「复核方法」。

**2026-09-10 收尾补充**：负责人已提供 `runs/post_recall/ood-probe-20260910/review-sheet-completed.md`，中文 24 个方向全部通过，文本与标签未改；三份已有评分的评价均精确复算。后续复核状态、原始提交和核验结果见 [runs/post_recall/ood-probe-20260910/README.md](../../runs/post_recall/ood-probe-20260910/README.md#review-replay)，初步迹象与限制见 [docs/reports/llm_judge_pilot_2026_09_10.md](../reports/llm_judge_pilot_2026_09_10.md#ood-human-review)。该段描述后续本地补充，原包中的 #24 文件仍为复核前快照。复核人姓名、实际日期和盲审情况未提供，保留缺失，不因姓名字段为空再要求重复标注。

本次没有重跑模型；既有评分仍如实标为复核提交前的运行。原待办中的“按需重跑”和增加另一开源模型是可选扩展，不因复核提交自动执行。下列命令仅供未来明确需要新推理时使用；当前 #24 本地复核、复算和报告已收尾，GitHub 关闭与合并状态另查。

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
