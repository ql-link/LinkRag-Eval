"""Independent verifier checks; all modifications stay in pytest temporary files."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).resolve().parents[1] / "verify_completed.py"
    spec = importlib.util.spec_from_file_location("completed_verifier_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tuple_values_preserve_real_ties_despite_id_order_and_respect_window(verifier):
    base = {"q": {"a": 1, "b": 2, "c": 8, "d": 0, "e": -1}}
    fused = {"q": {"a": 5, "b": 5, "c": 4, "d": 3, "e": 3}}
    judged = {"q": {"a": 1, "b": 1, "c": 4, "d": 2, "e": 2}}
    values, orders, missing = verifier.independent_l2(base, fused, judged, 2)
    assert missing == {"q": 0}
    assert orders["stage1_judge"]["q"] == ["a", "b", "c", "d", "e"]
    assert verifier.relation(values["stage1_judge"]["q"]["a"],
                             values["stage1_judge"]["q"]["b"]) == "model_tie"
    assert verifier.relation(values["stage1_judge"]["q"]["d"],
                             values["stage1_judge"]["q"]["e"]) == "model_tie"
    assert verifier.relation(values["stage1_judge"]["q"]["a"],
                             values["stage1_judge"]["q"]["c"]) == "strict_correct"
    assert orders["E0_judge"]["q"][:2] == ["b", "a"]
    assert verifier.relation(values["E0_judge"]["q"]["a"],
                             values["E0_judge"]["q"]["b"]) == "reverse"


def test_only_unavailable_inside_selected_window_forces_whole_query_fallback(verifier):
    base = {"q": {"a": 3, "b": 9, "c": 4}}
    fused = {"q": {"a": 5, "b": 5, "c": 4}}
    judged = {"q": {"a": 0, "b": None, "c": None}}
    values, orders, missing = verifier.independent_l2(base, fused, judged, 2)
    assert missing == {"q": 1}
    for arm in ("stage1_judge", "E0_judge"):
        assert values[arm]["q"] == fused["q"]
        assert orders[arm]["q"] == ["a", "b", "c"]
        assert verifier.relation(values[arm]["q"]["a"], values[arm]["q"]["b"]) == "model_tie"
    judged["q"]["b"] = 4
    _, orders, missing = verifier.independent_l2(base, fused, judged, 2)
    assert missing == {"q": 0}
    assert orders["stage1_judge"]["q"] == ["b", "a", "c"]


@pytest.fixture
def historical_args(verifier):
    pilot = verifier.PILOT
    return {
        "role": "confirmation", "level": "l2", "top_k": 10,
        "items": pilot / "items-stage1-top20/confirmation/confirmation.jsonl",
        "scores": pilot / "l2s-confirmation-judge/scores.jsonl",
        "baseline": pilot / "baseline/confirmation/scores.jsonl",
        "supervision": verifier.EXPERIMENT / "prepared/confirmation/supervision.jsonl",
        "stage1": pilot / "items-stage1-top20/confirmation/stage1-confirmation.jsonl",
        "result_dir": pilot / "l2s-confirmation-k10-v2",
    }


def test_existing_gpt_evaluation_agrees_with_raw_score_verifier(verifier, historical_args):
    result = verifier.verify_outputs(**historical_args)
    assert result["status"] == "passed" and result["orders_checked"] == 374
    metric = result["populations"]["official"]["methods"]["stage1_judge"]
    assert (metric["n"], metric["strict_correct"], metric["reverse"], metric["model_tie"]) == (371, 309, 59, 3)


@pytest.mark.parametrize("damage,message", [
    ("denominator", "per-query denominator differs"),
    ("outcome", "saved state contradicts raw scores"),
    ("order", "saved order differs from independent score keys"),
    ("aggregate", "aggregate counts differ"),
    ("fallback", "fallback denominator/count differs"),
])
def test_historical_output_corruption_is_detected(verifier, historical_args, tmp_path, damage, message):
    source = historical_args["result_dir"]
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    for name in ("results.json", "official-per-query.jsonl", "orders.jsonl"):
        shutil.copyfile(source / name, result_dir / name)
    if damage in {"denominator", "outcome"}:
        path = result_dir / "official-per-query.jsonl"
        data = verifier.rows(path)
        if damage == "denominator":
            data.pop()
        else:
            data[0]["stage1_judge"] = ("reverse" if data[0]["stage1_judge"] == "strict_correct"
                                        else "strict_correct")
        path.write_text("".join(json.dumps(row) + "\n" for row in data))
    elif damage == "order":
        path = result_dir / "orders.jsonl"
        data = verifier.rows(path)
        sequence = data[0]["orders"]["stage1_judge"]
        sequence[0], sequence[1] = sequence[1], sequence[0]
        path.write_text("".join(json.dumps(row) + "\n" for row in data))
    else:
        path = result_dir / "results.json"
        data = verifier.load(path)
        if damage == "aggregate":
            data["official"]["rankers"]["stage1_judge"]["pairwise"]["strict_correct"] += 1
        else:
            data["trigger"]["stage1_judge"]["fallback_queries"] += 1
        path.write_text(json.dumps(data))
    with pytest.raises(verifier.VerificationError, match=message):
        verifier.verify_outputs(**dict(historical_args, result_dir=result_dir))


@pytest.mark.parametrize("kind", ["8b", "confirmation"])
def test_cli_reports_incomplete_without_reading_partial_scores(verifier, tmp_path, monkeypatch, capsys, kind):
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    folder = tmp_path / ("runs/post_recall/open-judge-qwen3-8b-development-20260911" if kind == "8b"
                         else "runs/post_recall/open-judge-confirmation-20260911")
    folder.mkdir(parents=True)
    name = "execution-config.json" if kind == "8b" else "frozen-config.json"
    (folder / name).write_text("{}")

    def reject_partial(path):
        raise AssertionError("Partial score files must not be read")

    monkeypatch.setattr(verifier, "rows", reject_partial)
    monkeypatch.setattr(sys, "argv", ["verify_completed.py", "--kind", kind])
    assert verifier.main() == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err)["status"] == "incomplete"
    assert not (folder / "l1").exists()
