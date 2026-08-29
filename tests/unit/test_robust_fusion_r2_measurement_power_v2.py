from __future__ import annotations

from collections import Counter

from linkrag_eval.robust_fusion.r2_measurement_power_v2 import build_frame


def test_v2_frame_orthogonalizes_conflict_and_edit_within_each_cell() -> None:
    families = build_frame()[::2]
    for length_language in ("short_zh", "long_zh", "short_en", "long_en"):
        counts = Counter(
            (row["conflict_type"], row["edit_level"])
            for row in families
            if row["length_language"] == length_language
        )
        assert len(counts) == 16
        assert set(counts.values()) == {2}
