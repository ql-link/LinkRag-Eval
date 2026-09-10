# 非 NevIR OOD 小探针（issue #24）

用于检查开源 LLM judge 在普通英文主题及中文最小改写段落上的证据辨别能力；不改召回或 `judge_prompt_v1`。
这是一份人工构造的小探针，不代表通用能力，也不能证明模型训练数据中没有相似内容。

- `fixture.json`：英文原样复制的 8 段／6 查询，中文 12 对／24 段／24 查询，以及来源和复核状态。
- `README.md`：输入转换、后续运行与冻结规则；本次仅生成这两个文件，未运行 judge。

英文来源为 `runs/post_recall/english-capability-20260907/fixture.json`，原冻结时间完整保留在 `source.english.frozen_at`。
英文 `kind` 保持 `literal`／`paraphrase`；中文按 pair 标记 `negation`×4、`attribution`×2、`number`×2、`date`×2、`entity`×2。
中文名称、产品及事件均属虚构，同对两段是独立的反事实版本，不能拼成同一份事实记录。
每段 60–120 字符，每对仅有一处连续文本编辑，`difflib.SequenceMatcher(None, a, b).ratio()` 至少 0.85。

后续需先编写转换器：当前 `fixture.json` 不能直接传给 `judge --items`，转换器尚未编写。
依据 `src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py` 的 `build_items` 与现有 L1 文件 `runs/post_recall/llm-judge-pilot-20260910/items/l1-development.jsonl` 首行，每行是一个查询—段落对象：

| 字段 | 转换规则 |
| --- | --- |
| `source_query_id` | 查询 `id`，建议加 `ood_probe_v1:en:`／`ood_probe_v1:zh:` 前缀 |
| `chunk_id` | 英文文档 `id` 或中文 `doc_id`，使用同样的版本与语言前缀 |
| `pair_id` | 中文为带前缀的原 `pair_id`；英文无成对关系，按查询生成独立分组 ID |
| `query` | 原查询全文 |
| `passage` | 对应段落 `text` 全文 |
| `level` | 固定为 `l1`，表示沿用输入格式 |

现有 L1 首行还含 `prompt_version`、`model`、`effort`、`codex_version`，它们是运行元数据，不能把旧模型信息抄给新后端。
转换器只需以上六个基础字段；实际运行元数据由 runner 提供。`expected_doc_id` 留作评价标签，不进入 judge 提示词。
中文按每对 2 查询 × 2 段展开为 48 行，不能只导出目标段；英文按 6 查询 × 8 段展开为 48 行，共 96 行。
该转换复用 L1 行格式；现有 `items` 子命令依赖 NevIR 输入，不能直接负责本 fixture 的转换。

复核并转换后，在仓库根目录执行以下示例（占位路径均须替换，输出目录须尚不存在）：

```sh
python scripts/llm_judge_pilot.py judge --runner openai \
  --items <转换后的items.jsonl> --endpoint <服务根URL> --model <开源模型名> \
  --out <新的评分输出目录> --batch-size 1 --workers 4
```

需要鉴权时追加 `--api-key-env EVAL_JUDGE_API_KEY`，密钥放环境变量；endpoint 不附加 `/v1/chat/completions`。
judge 固定按原 `judge_prompt_v1` 对单个查询—段落给出 0–4 分，不能将两段或目标标签并入单个提示项。
中文分别报告严格目标胜出（平分不算正确）与双向全对；英文单独报告目标 top-1，不能混作中文成对指标。

目前 `assessment.reviewed_by` 为 `null`：所有 `expected_doc_id` 均为作者指定，使用前必须由第二人复核。
重点检查 `zh_p05/06` 的归属范围、`zh_p07/08` 的数值推断，以及 `zh_p11/12` 的近形实体名是否清楚可辨。
`frozen_at=2026-09-10` 是本版组装日期，不表示已通过复核；第二人确认文本、双向目标和单一差异后填写复核人并更新复核状态。
复核通过即冻结全文、查询和标签；之后有错须另起版本并说明原因，不能依据模型表现修改或删掉困难题。

## 结果登记（2026-09-10）

| 判别器 | 英文 6 查询 strict | 中文 24 方向 strict/reverse/tie | 中文 12 对双向全对 | 墙钟 | 产物 |
| --- | ---: | ---: | ---: | ---: | --- |
| GPT-6 low（`judge_prompt_v1`，批 40，3 并发） | 6/6 | 24/0/0 | 12/12 | 64 s | `judge-gpt6-low/`、`evaluation-gpt6-low.json` |
| Qwen3-14B-AWQ 不思考（vLLM 0.29，批 1，8 并发） | 6/6 | 16/1/7 | 6/12 | 19 s | `judge-qwen3-14b-awq/`、`evaluation-qwen3-14b-awq.json` |
| Qwen3-14B-AWQ 思考（同上，`--think`，max_tokens 4096） | 6/6 | 14/0/9（1 条截断不可用） | 4/12 | 169 s | `judge-qwen3-14b-awq-think/`、`evaluation-qwen3-14b-awq-think.json` |

说明：GPT-6 在本探针集上无一失误，故本集不能区分强判别器之间的差异，但可作为开源判别器的"及格线"参考。Qwen3-14B-AWQ 的错误几乎全是"平局"（两段同分），按类型看 number、entity、date 最弱（不思考：1/4、1/4、2/4），negation 不思考 8/8 但思考反而 4/8；样本量小（每类 4 个方向），仅作定性参考。英文 6 查询三种判别器均全对。
