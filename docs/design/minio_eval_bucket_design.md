# 评测产物 MinIO 桶 — 设计文档

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[phase1_design.md](phase1_design.md)（产物来源）、[trend_dashboard_design.md](trend_dashboard_design.md)（台账/看板）、[framework_design.md](framework_design.md)
> 范围：确认评测产物落 MinIO，并为其设计一个**专用桶**——桶名/配置、对象键布局、内容类型、清单对象（替代 list）、生命周期、访问与运维。
> 复用：基于项目现有 `src/services/storage`（`BaseObjectStorage` / `MinioStorage` / `StorageFactory`），不改生产存储接口。

---

## 一、结论先行

评测产物**入 MinIO 专用桶 `tolink-rag-eval`**，与生产文档桶（`tolink-rag-docs`）、博客桶（`tolink-blog`）物理隔离。三条决策：

1. **专用桶，不与生产数据混。** 评测产物会随轮次增长、需独立生命周期与权限，单独成桶最干净，沿用项目"按用途分桶"约定。
2. **复用现有存储抽象，不碰生产接口。** 通过 `StorageFactory.get_storage()` 拿 `BaseObjectStorage`，只用其 `upload_bytes` / `download_to_path` / `build_object_url`。`MinioStorage` 当前**不暴露 list、不自动建桶**——故用**清单/指针对象**代替列举，桶由运维预建。
3. **键布局承载层级与可追溯。** 以 `dataset → run-id → 产物` 分层，台账与基线指针各有固定键，保证"哪轮、什么口径、跑出什么"可定位。

---

## 二、桶与配置

新增一个桶配置常量，沿用现有 `MINIO_*` 命名：

```python
# src/config.py（Settings 内，与 MINIO_BUCKET_NAME / MINIO_BLOG_BUCKET 并列）
MINIO_EVAL_BUCKET: str = "tolink-rag-eval"
```

- **桶名**：`tolink-rag-eval`（环境可覆盖；多环境可加后缀如 `-dev`/`-prod` 隔离）。
- **STORAGE_TYPE**：复用全局开关。`minio` 走本设计；`local` 时评测产物退回本地 `.specs/`（见 §七 后端选择），开发零基建。
- **凭据/端点**：复用现有 `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/USE_SSL`，评测不另立账号。

---

## 三、对象键布局（key layout）

> **存储模式说明（与 [eval_storage_design.md](eval_storage_design.md) 对齐）**：**DB 模式（默认）**下，结构化数据（run/snapshot/指标）落独立 eval schema 表（`eval_run`/`eval_metric_result`），桶内只保留 `reports/`、`trend/`、`golden/` 导出与 `baselines/`/`index/` 指针；下方 `runs/{snapshot.yaml,result.json}` 与 `ledger/ledger.duckdb` 仅在**无 DB 的文件后端回退模式**下使用。

```
tolink-rag-eval/
├── runs/                              # 仅文件后端回退模式
│   └── <dataset>/
│       └── <run-id>/
│           ├── snapshot.yaml          # 配置快照（DB 模式下落 eval_run.config）
│           ├── result.json            # 机器可读结果（DB 模式下落 eval_metric_result 表）
│           └── report.html            # 人读报告 HTML（两模式都在桶里）
├── baselines/
│   └── <dataset>/
│       └── <config-key>.txt           # 基线指针：内容是某 run-id（按 config 分组各留各的）
├── ledger/
│   └── ledger.duckdb                  # 台账回退（DB 模式用 eval_metric_result 表，无此文件）
├── trend/
│   └── <dataset>/trend.html           # 趋势看板（自包含 Chart.js）
├── golden/
│   └── <dataset>@<ingestion>.jsonl    # 黄金集冻结导出（不可变快照）
└── index/
    └── runs.jsonl                     # 运行清单（替代 list API，见 §四；DB 模式可改查表）
```

约定：

- `<dataset>`：黄金集名；`<run-id>`：`<yyyymmdd-hhmm>-<gitsha>-<标签>`。
- `<config-key>`：config 维度规范化后的稳定串（如 `sparse=remote_bge_m3__topk=20__src=bm25,dense,sparse`），保证"同口径基线"可寻址（呼应趋势看板"同 config 才比"）。
- 单轮三件套同前缀 `runs/<dataset>/<run-id>/`，与本地 `.specs/` 布局同构，便于双后端互导。

内容类型（`upload_bytes` 的 `content_type`）：`.yaml`→`application/yaml`、`.json`→`application/json`、`.md`→`text/markdown`、`.html`→`text/html`、`.duckdb`→`application/octet-stream`、`.txt`→`text/plain`。

---

## 四、清单对象：替代缺失的 list API

`MinioStorage` 不提供 `list_objects`，而趋势/基线需要"枚举历轮"。**不扩生产存储接口**，改用两个自维护对象：

- **运行清单 `index/runs.jsonl`**：每完成一轮，**追加一行** `{run_id, dataset, ts, git_sha, config_key, layers}`。台账重建、看板选轮、清理都读它。追加幂等（按 `run_id` 去重）。
- **基线指针 `baselines/<dataset>/<config-key>.txt`**：内容仅一个 run-id。`load_baseline` 读指针 → 拼出 `runs/.../result.json` 键 → 下载。换基线 = 覆写该指针对象。

> 这样列举/基线解析都落在评测自管的对象上，`BaseObjectStorage` 三个方法足够，生产接口零改动。

---

## 五、写入流程（一轮评测结束时）

```
run 结束 → ObjectStorageResultStore:
  1. upload snapshot.yaml / result.json / report.html  → runs/<dataset>/<run-id>/
  2. 下载 index/runs.jsonl → 追加本轮行（按 run_id 去重）→ 回传
  3. MetricsLedger.append(result) → 更新 ledger.duckdb（下载→写→回传）
  4. trend_report 生成 trend.html → 回传 trend/<dataset>/
  5.（可选）若本轮设为基线：覆写 baselines/<dataset>/<config-key>.txt
```

并发：评测非高并发，台账/清单以**单轮串行**为前提；如需并行多轮，给 ledger/index 加对象级简单锁或改用 parquet 分区追加（各轮独立文件，查询时合并）。

---

## 六、生命周期与容量

- **保留策略**：`runs/` 与 `report.html` 可设对象生命周期（如 N 天过期或转冷存）；**`ledger` 与 `baselines` 不过期**（趋势的真相依赖）。MinIO 桶级 lifecycle 规则由运维配置。
- **台账可重建**：`ledger.duckdb` 即便丢失，可从 `runs/**/result.json` 全量 `rebuild`，故它是缓存而非唯一真相。
- **体量**：单轮三件套通常 KB~MB 级；若开启 top-k 候选 dump（调试用）可能偏大，建议另置 `runs/<dataset>/<run-id>/debug/` 并优先纳入过期策略。

---

## 七、后端选择与依赖边界

`ResultStore` 协议（phase0）下挂两个后端，按 `STORAGE_TYPE` 选：

```
src/evaluation/storage/
├── filesystem.py        # FilesystemResultStore（local：写 .specs/）
└── object_store.py      # ObjectStorageResultStore（minio/oss：复用 StorageFactory.get_storage()）
```

- `object_store.py` 仅依赖 `src/services/storage`（拿 `BaseObjectStorage`）与 `settings.MINIO_EVAL_BUCKET`，**不碰 src.core**。
- **依赖方向**：引入 `evaluation → services` 依赖（与 `recall_adapter → api` 同类取舍）。`services/storage` 是通用工具层，可接受；在 import-lint 白名单显式放行 `evaluation/storage → services/storage` 这一条。

---

## 八、运维前置（ops）

1. **预建桶**：`MinioStorage` 不自动建桶，部署时需手动创建 `tolink-rag-eval`（或加一段一次性 bootstrap：`head_bucket` 失败则 `create_bucket`，仅评测侧用，不污染生产 `MinioStorage`）。
2. **权限**：评测读写限于该桶；如需团队只读看板，可对 `trend/` 前缀开匿名/只读策略，配合 `build_object_url` 分享链接。
3. **多环境隔离**：dev/prod 用不同桶名或不同 MinIO 实例，避免基线/台账互串。
4. **配置回流**：`MINIO_EVAL_BUCKET` 写入 `.env.example` 与 ops 文档（`docs/ops/`），M4 收口时随口径一并回流。

---

## 九、完成判据（Definition of Done）

1. `MINIO_EVAL_BUCKET` 在 `Settings` 与 `.env.example` 声明，桶已预建。
2. `ObjectStorageResultStore` 经 `StorageFactory.get_storage()` 读写 §三 键布局，三件套 + ledger + trend 落桶正确。
3. `index/runs.jsonl` 幂等追加；`baselines/<dataset>/<config-key>.txt` 指针可读写、`load_baseline` 据此还原结果。
4. `STORAGE_TYPE=local` 时无缝退回 `FilesystemResultStore`（.specs/），两后端键/路径同构可互导。
5. import-lint 放行 `evaluation/storage → services/storage`，其余方向不破。
