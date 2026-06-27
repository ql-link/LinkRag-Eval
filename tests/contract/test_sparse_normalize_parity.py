"""漂移守卫:eval 自持的 normalize 必须与生产 ``normalize_lexical_weights`` 同输入同输出。

eval 为保依赖边界(llm 模块零 rag import)重实现了清洗;本测试确保它和生产口径一字不差,
否则 eval 的 sparse 分数与线上不可比。需 toLink-Rag 可 import,故标 contract。
"""

from __future__ import annotations

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")

from linkrag_eval.llm.normalize import normalize_lexical_weights as eval_norm  # noqa: E402

SAMPLES = [
    {0: 0.9, 5: 0.3, 2: 0.7, 9: 0.1},
    {10: 0.5, 3: 0.5, 1: 0.5},  # 同权重,验 index 次序
    {100: 0.01, 200: 0.99, 7: 0.42, 8: 0.0},  # 含 0 权重(应丢)
]


@pytest.mark.parametrize("weights", SAMPLES)
@pytest.mark.parametrize("top_k,min_weight", [(256, 0.0), (2, 0.0), (256, 0.2)])
def test_parity_with_production(weights, top_k, min_weight) -> None:
    from src.core.encoding.sparse.encoder import normalize_lexical_weights as prod_norm

    prod = prod_norm(weights, top_k=top_k, min_weight=min_weight)
    mine = eval_norm(weights, top_k=top_k, min_weight=min_weight)
    assert mine.indices == prod.indices
    assert mine.values == prod.values
