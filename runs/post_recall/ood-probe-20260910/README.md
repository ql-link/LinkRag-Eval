# 非 NevIR OOD 小探针（issue #24）

用于检查开源 LLM judge 在普通英文主题及中文最小改写段落上的证据辨别能力；不改召回或 `judge_prompt_v1`。
这是一份人工构造的小探针，不代表通用能力，也不能证明模型训练数据中没有相似内容。

- `fixture.json`：英文原样复制的 8 段／6 查询，中文 12 对／24 段／24 查询，以及来源和复核状态。
- `items.jsonl`：已展开的 96 条查询—段落输入；`judge-*/` 和 `evaluation-*.json` 保存原判断及评价，均为本地忽略产物。
- `review-sheet.md`／`review-sheet-completed.md`：原空白表与负责人提供的已完成中文复核，分别保留。
- `review-validation.json`：复核表对应检查、既有评价的精确复算结果和实际命令。

英文来源为 `runs/post_recall/english-capability-20260907/fixture.json`，原冻结时间完整保留在 `source.english.frozen_at`。
英文 `kind` 保持 `literal`／`paraphrase`；中文按 pair 标记 `negation`×4、`attribution`×2、`number`×2、`date`×2、`entity`×2。
中文名称、产品及事件均属虚构，同对两段是独立的反事实版本，不能拼成同一份事实记录。
每段 60–120 字符，每对仅有一处连续文本编辑，`difflib.SequenceMatcher(None, a, b).ratio()` 至少 0.85。

转换器和评价器已在 `scripts/llm_judge_pilot.py probe-items`／`probe-evaluate` 实现。转换器保留 fixture 中的 query／document ID；英文 `pair_id` 为查询 ID，中文方向分组为 `<pair_id>-<query_id>`，不另加前缀。每行沿用 L1 格式，保留 `expected`／`probe_set`／`kind` 供评价；模型元数据先为 null，由 runner 写入，目标标签不进入提示词。
中文按每对 2 查询 × 2 段展开为 48 行，英文按 6 查询 × 8 段展开为 48 行，共 96 行。复现已有评价使用下方[离线复算](#review-replay)，不需要新推理。

复核并转换后，在仓库根目录执行以下示例（占位路径均须替换，输出目录须尚不存在）：

```sh
python scripts/llm_judge_pilot.py judge --runner openai \
  --items <转换后的items.jsonl> --endpoint <服务根URL> --model <开源模型名> \
  --out <新的评分输出目录> --batch-size 1 --workers 4
```

需要鉴权时追加 `--api-key-env EVAL_JUDGE_API_KEY`，密钥放环境变量；endpoint 不附加 `/v1/chat/completions`。
judge 固定按原 `judge_prompt_v1` 对单个查询—段落给出 0–4 分，不能将两段或目标标签并入单个提示项。
中文分别报告严格目标胜出（平分不算正确）与双向全对；英文单独报告目标 top-1，不能混作中文成对指标。

2026-09-10 已接收负责人提供的完成表，中文 24 个方向均通过并有理由，包括归属、数值推断和近形实体检查；文本、查询与目标均未改变，`assessment.review_status=completed_all_pass`。复核人姓名和实际复核日期未提供，`reviewed_by`／`reviewed_at` 保留 null；`review_received_at` 只表示收件日期，不能推定复核时间或盲审情况。
`frozen_at=2026-09-10` 仍为本版组装日期。复核收件后保持本版全文、查询与标签；之后有错须另起版本并说明原因，不能依据模型表现修改或删掉困难题。

## 结果登记（2026-09-10）

| 判别器 | 英文 6 查询 strict | 中文 24 方向 strict/reverse/tie | 中文 12 对双向全对 | 墙钟 | 产物 |
| --- | ---: | ---: | ---: | ---: | --- |
| GPT-6 low（`judge_prompt_v1`，批 40，3 并发） | 6/6 | 24/0/0 | 12/12 | 64 s | `judge-gpt6-low/`、`evaluation-gpt6-low.json` |
| Qwen3-14B-AWQ 不思考（vLLM 0.29，批 1，8 并发） | 6/6 | 16/1/7 | 6/12 | 19 s | `judge-qwen3-14b-awq/`、`evaluation-qwen3-14b-awq.json` |
| Qwen3-14B-AWQ 思考（同上，`--think`，max_tokens 4096） | 6/6 | 14/0/9（1 条截断不可用） | 4/12 | 169 s | `judge-qwen3-14b-awq-think/`、`evaluation-qwen3-14b-awq-think.json` |

以上为复核提交前的原模型运行，随后离线复算数值不变。Qwen3-14B-AWQ 在本批中文题上的未胜出多为平局；number、entity、date 不思考分别为 1/4、1/4、2/4，negation 不思考 8/8、思考 4/8。negation 有 8 个方向，其余每类 4 个方向，同对两个方向相关，不能当作独立样本外推。英文 6 查询三种配置均全对，只是小规模普通主题对照；这里未执行融合前 20 的完整重排流程。原思考配置的 token 上限为 4096，也不能写成后来确认实验的 6144 配置。

<a id="review-replay"></a>
## 中文复核接收与离线复算（2026-09-10）

已检查 12 对、24 个方向的字段及正文，完成表仅填写最后两列；所有预期目标保留，未增删或改题。24 段长度为 99–107 字符，每对只有一处连续编辑，最小相似度 0.980769。英文文本与查询仍与原来源一致，本次没有新增英文人工复核。

在代码 `50e7aa33ec8360e1e309f60ca43be1a6e81c38b5` 上从 fixture 重建 96 条输入，分别调用原 `probe-evaluate` 评价三份缓存，三组完整结果对象与原评价精确相同。19 项收件与复算检查通过；检查及四次离线 CLI 合计约 0.56 秒，新增模型请求为 0，原模型成本保留在上表及各自 `summary.json`。这验证了已有结果的计算，未新增人工判断或模型推理。实际命令、聚合指标和限制保存于 [review-validation.json](review-validation.json)。

以下命令只读本目录输入，输出到新建临时目录；需要本机已有的原评分文件：

```sh
ood_probe_dir=runs/post_recall/ood-probe-20260910
ood_replay_dir=$(mktemp -d "${TMPDIR:-/tmp}/linkrag-ood-replay.XXXXXX")
.venv/bin/python scripts/llm_judge_pilot.py probe-items \
  --fixture "$ood_probe_dir/fixture.json" --output "$ood_replay_dir/items.jsonl"
for ood_model in gpt6-low qwen3-14b-awq qwen3-14b-awq-think; do
  .venv/bin/python scripts/llm_judge_pilot.py probe-evaluate \
    --items "$ood_replay_dir/items.jsonl" --scores "$ood_probe_dir/judge-$ood_model/scores.jsonl" \
    --output "$ood_replay_dir/evaluation-$ood_model.json"
done
```

负责人只提供完成表，复核人姓名、实际日期及是否看过模型结果未知。收件不改变原运行先于本次提交的事实；不称为复核后新跑的独立确认，也不据此更换当前 Qwen 主方案。初步迹象与研究边界见[报告 §10.2.1](../../../docs/reports/llm_judge_pilot_2026_09_10.md#ood-human-review)。

## 复核方法（人工，约 30 分钟）

本轮已完成；以下保留原复核方法供追溯。原要求是在 `review-sheet.md` 对 24 行逐行判断，每行只问三个问题：

1. **应答段真的能回答该查询吗？** 只看「应答段」那一段正文，不看另一段。答案必须能从段落中直接读出，不需要外部知识。
2. **另一段是否确实回答不了或答反？** 把同一查询放到另一段上，结果应是"不成立"或"答案相反"，而不是"也能答"。若两段都能答，标记不通过。
3. **查询是否自然、不泄题？** 查询不应把差异词直接抄进去以至于靠字面匹配就能选对（例如问"哪家没有……"时正文正好含"没有"是允许的，但查询不能整句复述段落）。

任何一行不通过，在备注写明原因，由作者改写该对后重新复核；不要只改标签迁就段落。全部通过后：

- 收录完成表，核对文本、查询、目标与原 fixture 一致，更新 `assessment.review_status`；复核人姓名与实际日期只有在提供后才填写，收件日期另记；
- 之后本目录的 `fixture.json` 与 `items.jsonl` 视为冻结，任何改动需另起版本号（`ood_probe_v2`）并重新跑判断器。

英文 6 题沿用 `english-capability-20260907` 的既有标签，不在本次复核范围。
