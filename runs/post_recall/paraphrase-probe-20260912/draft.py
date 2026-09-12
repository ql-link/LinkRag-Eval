"""Rebuild the initial AI-authored drafts from the two supplied source files.

This does not create human decisions. Later revisions belong in the JSONL,
with a new revision and an explicit supersedes link, not in the source files.
"""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAMILIES = [
    (
        "Mira Vale",
        "Noah Stone",
        "recites poems",
        "read",
        "performs recitations of poems",
        "Lena Brook",
        "Felix Reed",
        "朗诵诗歌",
        "阅读",
    ),
    (
        "Clara Moss",
        "Owen Reed",
        "repairs clocks",
        "swim",
        "fixes clocks",
        "Diana Hart",
        "Marcus Bell",
        "修理钟表",
        "游泳",
    ),
    (
        "Nora Lake",
        "Evan Hill",
        "paints murals",
        "drive",
        "creates murals by painting",
        "Ada Frost",
        "Leo Pine",
        "绘制壁画",
        "驾驶",
    ),
    (
        "Elena Wood",
        "Iris West",
        "writes songs",
        "dance",
        "engages in writing songs",
        "Vera Cole",
        "Tessa Lane",
        "创作歌曲",
        "跳舞",
    ),
]


def write_rows(path, rows):
    with path.open("x") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    for name in ("scenes-original.jsonl", "scenes-paraphrased.jsonl", "source-audit.json"):
        if (HERE / name).exists():
            raise FileExistsError(f"preserve existing preparation: {HERE / name}")
    sources = json.loads((HERE / "source/control-scenes.json").read_text())
    texts = [
        json.loads(line)
        for line in (HERE / "source/control-texts.jsonl").read_text().splitlines()
        if line.strip()
    ]
    expected = set()
    for scene in sources:
        expected.update(("paragraph", text) for text in scene["paragraphs"])
        expected.update(("query", text) for text in scene["queries"] + scene["paraphrases"])
    actual = [(row["kind"], row["text"]) for row in texts]
    if set(actual) != expected or len(actual) != len(set(actual)):
        raise ValueError("control-texts is not the exact deduplicated scene-text inventory")
    if len(sources) != 12 or len({s["probe_id"] for s in sources}) != 12:
        raise ValueError("expected exactly twelve unique original scenes")
    originals, variants = [], []
    for source in sources:
        index = int(source["probe_id"].rsplit("-", 1)[1]) - 1
        a, b, action, ability, synonym, na, nb, action_zh, ability_zh = FAMILIES[index]
        core = {
            "source_scene_id": source["probe_id"],
            "category": source["category"],
            "content_family": f"family-{index + 1}",
            "language": "en",
            "expected_preferences": source["intended_entity_preferences"],
            "source_construction_status": source["construction_status"],
            "review_state": "pending_human_review",
            "revision": 1,
            "supersedes": None,
        }
        original = dict(
            core,
            version_id=source["probe_id"] + "--original-v1",
            rewrite_type="original",
            paragraphs=source["paragraphs"],
            queries=source["queries"],
            authored_by={"actor": "source AI author", "model": None},
            source_existing_query_paraphrases=source["paraphrases"],
            drafting_notes="Original paragraphs and queries retained verbatim.",
        )
        originals.append(original)
        replacements = [
            (action, synonym),
            (f"cannot {ability}", f"is unable to {ability}"),
            (f"can {ability}", f"is able to {ability}"),
        ]
        paragraphs = []
        for paragraph in source["paragraphs"]:
            for old, new in replacements:
                paragraph = paragraph.replace(old, new)
            paragraphs.append(paragraph)
        authored = {
            "actor": "Codex assistant",
            "model": None,
            "model_note": "Exact authoring model ID not exposed in this session.",
            "date": "2026-09-12",
        }
        variants.append(
            dict(
                core,
                version_id=source["probe_id"] + "--synonym-v1",
                rewrite_type="synonym",
                paragraphs=paragraphs,
                queries=[
                    f"Which person {synonym} and is unable to {ability}?",
                    f"Which person is able to {ability} and {synonym}?",
                ],
                authored_by=authored,
                drafting_notes="Rephrased actions and ability; reversed positive "
                "query condition order. Human review must check equivalence.",
            )
        )
        renamed = source["paragraphs"] + source["queries"]
        renamed = [text.replace(a, na).replace(b, nb) for text in renamed]
        variants.append(
            dict(
                core,
                version_id=source["probe_id"] + "--entity-rename-v1",
                rewrite_type="entity_rename",
                paragraphs=renamed[:2],
                queries=renamed[2:],
                entity_mapping={a: na, b: nb},
                authored_by=authored,
                drafting_notes="Only proper names replaced consistently. Original "
                "queries contain no names, so both queries deliberately stay unchanged.",
            )
        )
        for row in [original, *variants[-2:]]:
            primary, secondary = (na, nb) if row["rewrite_type"] == "entity_rename" else (a, b)
            row["chinese_aid"] = {
                "identity": "AI 辅助释义，非人工结论；以英文正文为准。",
                "paragraphs": [
                    (
                        f"{primary} {action_zh}；{primary} 不能{ability_zh}；"
                        f"{secondary} 能{ability_zh}。"
                    ),
                    (
                        f"{primary} {action_zh}；{secondary} 不能{ability_zh}；"
                        f"{primary} 能{ability_zh}。"
                    ),
                ],
                "queries": [
                    f"谁既{action_zh}，又不能{ability_zh}？",
                    f"谁既{action_zh}，又能{ability_zh}？",
                ],
            }
    write_rows(HERE / "scenes-original.jsonl", originals)
    write_rows(HERE / "scenes-paraphrased.jsonl", variants)
    audit = {
        "status": "structurally_verified_semantic_review_pending",
        "prepared_at": datetime.now(UTC).isoformat(),
        "input_directory": str((HERE / "source").resolve()),
        "input_files": ["control-scenes.json", "control-texts.jsonl"],
        "source_scenes": len(sources),
        "source_text_rows": len(texts),
        "source_text_inventory_exact": True,
        "categories": dict(Counter(s["category"] for s in sources)),
        "content_families": 4,
        "draft_variants": len(variants),
        "logical_scores_per_model": 144,
        "human_submissions": 0,
        "note": "Only the two requested input files were read; no earlier scores used. "
        "Four content families share three syntactic templates; not 12 independent topics.",
    }
    with (HERE / "source-audit.json").open("x") as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
