"""lexical weights 清洗(eval 自持,口径对齐生产 ``normalize_lexical_weights``)。

把 ``{token_id: weight}`` 清洗成稳定排序的 :class:`SparseVec`:按 min_weight 过滤、
按权重取 top_k、最终按 index 升序(Qdrant 写入习惯)。同一 token 多次出现保留最大权重。

为什么在 eval 内重实现而非 import rag:保持 llm 模块零 rag import(依赖边界)。漂移由
tests/contract/test_sparse_normalize_parity.py 钉死——与生产函数同输入必须同输出。
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from linkrag_eval.compute.protocol import SparseVec


class SparseCleaningError(ValueError):
    """lexical weights 非法,或过滤后无任何可写维度。"""


def normalize_lexical_weights(
    weights: Mapping[str | int, float],
    *,
    top_k: int = 256,
    min_weight: float = 0.0,
) -> SparseVec:
    """清洗 lexical weights → indices 升序的 SparseVec。

    Args:
        weights: token_id→权重映射(token_id 可为 str 或 int)。
        top_k: 按权重保留的最大维度数;>0 生效,0 不截断。
        min_weight: 最小保留权重,低于则过滤。

    Raises:
        SparseCleaningError: 非映射 / token_id 非法 / 权重非法 / 过滤后为空。
    """
    if not isinstance(weights, Mapping):
        raise SparseCleaningError("lexical weights 不是映射。")

    merged: dict[int, float] = {}
    for raw_index, raw_value in weights.items():
        try:
            index = int(raw_index)
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise SparseCleaningError(f"非法 lexical 项:{raw_index!r} -> {raw_value!r}。") from exc
        if index < 0:
            raise SparseCleaningError(f"token index 必须非负:{index}。")
        if not math.isfinite(value):
            raise SparseCleaningError(f"权重必须有限:{value}。")
        if value <= 0 or value < min_weight:
            continue
        previous = merged.get(index)
        if previous is None or value > previous:
            merged[index] = value

    if not merged:
        raise SparseCleaningError("过滤后稀疏向量为空。")

    items = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))
    if top_k > 0:
        items = items[:top_k]
    items.sort(key=lambda kv: kv[0])
    return SparseVec(
        indices=[i for i, _ in items],
        values=[float(v) for _, v in items],
    )
