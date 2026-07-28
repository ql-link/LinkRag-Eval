# Query 重写配对基准 V1

## 目的

本基准用于验证 Query 重写是否真实提升召回。所有方案必须在同一条原始 Query、同一组 qrel、同一20k语料范围和同一冻结召回参数下进行配对比较。

该基准只用于 tune 和开发验证，不作为新的 blind。当前来源数据已经参与过历史分析，后续正式验收仍需新建未揭盲的 realistic blind v2。

## 固定数据

输出目录：

`runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/`

| 文件 | 数量 | 用途 |
| --- | ---: | --- |
| `original_full_272.jsonl` | 272 | 完整配对评测，保留原始多 qrel |
| `original_single_chunk_206.jsonl` | 206 | 单 canonical chunk 主对比 |
| `original_smoke_40.jsonl` | 40 | 快速开发验证，五类 `type_hint` 各8条 |
| `benchmark_manifest.json` | 1 | 数据来源、哈希、分布和评测纪律 |

## 配对纪律

1. 重写模型只能读取原始 Query 及显式用户上下文，禁止读取 `expected_chunk_ids`、目标 chunk 正文或候选排序。
2. 原始版本和重写版本必须保持相同的样本ID、qrel、用户路由ID和 dataset scope。
3. 完整272条含多 qrel，主比较使用 `Hit@10` 和 `MRR`；`Recall@10` 单独报告。
4. 单 chunk 206条中 `Recall@10` 与 `Hit@10` 可直接配对比较，作为重写收益 headline。
5. 任何重写方案必须同时报告新增命中、保持命中、丢失命中和净提升。
6. Prompt、模型、温度、输出schema和重写结果必须缓存并写入运行快照。

## 重建命令

```bash
python3 scripts/prepare_query_rewrite_benchmark.py \
  --source runs/golden_v2/scale_100k_991004/scale_20k_overnight/realistic_tune_scope_992003.jsonl \
  --out-dir runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1
```

生成后必须核对 `benchmark_manifest.json` 中的SHA-256。后续实现不得静默修改这三个JSONL文件。

## 重写计划生成

配置独立的 `EVAL_REWRITE_*`，不得复用生产 `llm_user_config`：

```bash
PYTHONPATH=src python3 -m linkrag_eval.cli query-rewrite generate \
  --golden runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/original_smoke_40.jsonl \
  --out runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/rewrite_plans_smoke_40.jsonl \
  --report-out runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/rewrite_plans_smoke_40_report.json
```

模型只收到 `sample_id`、原始 Query 和问题类型。输出包含 Dense/Sparse/BM25 三路 Query、动态权重、候选保护名额和置信度，不包含推理过程。

若尚未单独配置 `EVAL_REWRITE_*`，可在纯 eval 实验中显式复用 Judge 端点凭证：

```bash
... query-rewrite generate --use-judge-endpoint --model deepseek-reasoner
```

该开关不读取生产用户模型配置；正式批量实验仍建议配置独立 `EVAL_REWRITE_*`，便于成本和模型指纹审计。

## 配对评测

```bash
PYTHONPATH=src python3 -m linkrag_eval.cli query-rewrite evaluate \
  --golden runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/original_smoke_40.jsonl \
  --plans runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/rewrite_plans_smoke_40.jsonl \
  --out-dir runs/golden_v2/scale_100k_991004/scale_20k_overnight/query_rewrite_benchmark_v1/pair_eval_smoke_40 \
  --precheck
```

默认行为是每一路共享一次原始 Query 候选，只额外请求该路的重写 Query，再按 `chunk_id` 合并取最高原始分。这样原始 Query 始终兜底，同时避免前后两侧重复请求造成不公平漂移。`--rewrite-only` 仅用于消融实验。

由于合并候选后重新归一化仍可能把原始正确结果挤出Top10，重写侧默认额外保护原始 Hybrid Top5。可通过 `--original-protected-top-k` 调整；该值只能在 tune 上选择。

配对报告必须标记 `clean/non-clean`。任一侧存在分路失败时，结果只能用于排障，不能用于宣称重写提升。

消融实验：

- `--default-weights --no-candidate-protection`：只测三路 Query 重写。
- `--no-candidate-protection`：测 Query 重写加动态权重。
- 默认：测 Query 重写、动态权重和候选保护的完整组合。
