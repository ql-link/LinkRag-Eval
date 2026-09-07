# 模型入口

当前两个模型统一命名为**中文基线**和**英文基线**，物理目录都在本目录下。研究语言与比较原则见[研究计划 §1.2](../docs/plans/post-recall-research-plan.md#12-当前研究语言与模型范围)，动态进度见[当前状态](../docs/CURRENT_STATUS.md)。

| 当前模型 | 特征版本 | 实际模型包 | 用途 |
| --- | --- | --- | --- |
| 中文基线（原 A） | `candidate_difference_v3`（legacy） | [chinese-baseline/](chinese-baseline/manifest.json) | 固定的原始工程参照 |
| 英文基线（英文适配版） | `candidate_difference_v3_en_v1`，规则 `english_basic_v1` | [english-baseline/](english-baseline/manifest.json) | 后续英文研究的工作起点 |

目录与展示名已修改，包内权重、规则、契约和历史版本号保持不变：中文为 `candidate-difference-v3-20260728-final33`，英文为 `nevir-english-same38-20260907`。历史 B 和 legacy 控制组仍保留在原 `runs/` 位置，不列作当前模型。

两个入口均使用已有加载器，必须配套选择特征版本（以下路径相对仓库根目录）：

```python
from linkrag_eval.retrieval.learning_to_rank.online import LambdaMartOnlineRanker

chinese_baseline = LambdaMartOnlineRanker(
    "models/chinese-baseline",
    feature_version="candidate_difference_v3",
)
english_baseline = LambdaMartOnlineRanker(
    "models/english-baseline",
    feature_version="candidate_difference_v3_en_v1",
)
```

后续研究显式选择 `english_baseline`；底层 API 的 legacy 默认值保持不变，没有自动语言识别或模型切换。基线命名不改变已有实验结论。

模型包不可回写，接入前使用现有契约验证：

```bash
linkrag-eval ltr validate-bundle --model-dir <实际模型包目录>
```

中文基线沿用原 Git 管理方式；英文基线仍为被忽略的本地产物，不会随 clone 自动出现。英文训练记录、候选、矩阵和分数仍留在原实验目录，见[实验说明](../runs/post_recall/nevir-english-features-20260907/README.md)。

历史记录中的旧路径对应如下；没有保留旧目录或软链接：

| 原路径 | 当前位置 |
| --- | --- |
| `models/candidate-difference-v3-20260728-final33/` | `models/chinese-baseline/` |
| `runs/post_recall/nevir-english-features-20260907/comparison/english/model-b/` | `models/english-baseline/` |

为保持当前重放可用，英文 `selection.json` 的模型／策略路径和比较配置中的策略路径已同步；历史命令、指标与诊断记录保留当时内容，追溯旧路径时按上表定位。
