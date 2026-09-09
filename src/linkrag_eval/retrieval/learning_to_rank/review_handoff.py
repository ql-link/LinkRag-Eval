"""Validate and distribute existing blind packets without resampling identities."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics import _review_html
from linkrag_eval.retrieval.learning_to_rank.review_schema import (
    PAIR_REASON_CODES,
    REASON_SCHEMA_VERSION,
    REASON_TYPES,
    STORAGE_SUFFIX,
    VALIDATION_POLICY_VERSION,
    structured_errors,
    structured_missing,
)

PUBLIC_FILES = ("review.html", "cases.jsonl", "blank-answers.jsonl")
REVIEWERS = ("reviewer_1", "reviewer_2")

NEUTRAL_INSTRUCTIONS = """# 英文证据独立审阅：使用说明

本任务判断英文查询与两段正文的证据适用性。请独立完成整份 76 条，每条先理解查询具体要求，再分别判断两段是否支持这些要求，并给出对应原文摘录和简短理由。

不凭主题相似、相同人名或常识猜答案；以提供的正文为依据，不上网补充事实。必要时说明条件或行为属于谁，但不要假定所有案例都是同一种问题。

“明确不满足”“没有提供足够证据”和“无法确定”不同。允许两段都支持、都不足、两段相当或有歧义，不强迫每题一正一负。答案词相同也不代表证据同样适用。

请沿用表单字段，填写依据和不确定原因；不需要另造关系结构或给候选打模型分数。若此前见过某例答案或分析，请在该题的理由中注明。

请本人独立阅读，不使用 ChatGPT、Codex 或其他模型代为判断，不查看另一审阅者意见或官方答案。身份按实际填写，可使用稳定代号。

用已有导出功能保存结果并交回完整导出文件，不只交截图。只有部分完成时，明确说明进度；不要填造未审项目。先各自提交，再讨论分歧。

## 打开与填写

1. 完整解压自己收到的 ZIP，进入其中的审阅目录；使用桌面 Chrome、Edge 或 Firefox 打开 `review.html`。不要在 ZIP 预览中填写。
2. 填写姓名或稳定代号，审阅者类型选择“人类审阅者”。每人独立完成全部 76 条。
3. 分别判断 X、Y；选中对应段落中的证据文字，点击“将所选原文记为证据”，自动保存摘录和位置，再填写简短理由。证据不足时允许没有摘录，但必须说明缺少什么。
4. 完成查询歧义、两段判断和相对偏好。已独立完成的题选择“独立复核”；无法确定的题可选“争议保留”，说明原因。未审的题保持“待复核”。
5. 点击“保存当前”后再离开。上一题／下一题也会保存。刷新后从第一题显示，已保存答案仍在；可以逐题前进查看。

位置按 Unicode 字符计数，从 0 开始，结束位置不含该字符；优先使用原文选中功能，不手算。页面会拒绝与摘录不一致的位置。

## 保存、恢复与交回

记录保存在同一浏览器、同一打开位置的本地存储中。不要使用无痕模式、清理站点数据或在审阅中途改名／移动目录／更换端口。已有草稿请先下载备份，不要覆盖或删除。

点击“下载结果”，保存文件名末尾为 `-answers.json` 的完整 JSON。建议每次离开前都下载；页面目前没有 JSON 导入功能，下载文件用于备份与交付，不能承诺换设备后自动恢复。

最后把该 JSON 原文件交回负责人；如有部分未完成、既往曝光或多个版本，请附一段说明并明确哪个是本次最终版本。不要只交截图，也不要修改匿名编号、X/Y 或文本。`blank-answers.jsonl` 是原始空白模板，不是完成后的提交。

## 本地文件无法正常打开或保存时

需要安装 Python 3。在终端先进入解压后、**仅包含自己公共材料**的目录，然后运行：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory .
```

浏览器打开 `http://127.0.0.1:8765/review.html`。保持终端运行，结束后按 Ctrl+C 停止。以后续审使用相同目录、浏览器、地址和端口。

仅在这个审阅目录启动；不要从项目根目录启动，不要公开端口。离线文件与 localhost 使用不同存储位置，开始填写后不要来回切换。
"""


class ReviewHandoffError(ValueError):
    """Packet content or identity cannot be safely associated."""


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(rows: list[dict], key: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ReviewHandoffError(f"invalid/duplicate {key}")
        result[value] = row
    return result


def validate_existing_packet(
    folder: Path, mapping_path: Path, reviewer: str,
    prepared: list[dict], bodies: dict,
) -> dict:
    cases = read_rows(folder / "cases.jsonl")
    forms = read_rows(folder / "blank-answers.jsonl")
    mapping_rows = read_rows(mapping_path)
    source = unique(prepared, "source_query_id")
    mapped = unique(mapping_rows, "case_id")
    unique(cases, "case_id")
    unique(forms, "case_id")
    if (len(cases) != len(prepared)
            or [c["case_id"] for c in cases] != [m["case_id"] for m in mapping_rows]
            or [c["case_id"] for c in cases] != [f["case_id"] for f in forms]
            or set(unique(mapping_rows, "source_query_id")) != set(source)):
        raise ReviewHandoffError("packet query count, order or identity mismatch")
    for case, form in zip(cases, forms, strict=True):
        if set(case) != {"case_id", "query", "paragraphs"}:
            raise ReviewHandoffError("unexpected public case fields")
        m = mapped[case["case_id"]]
        original = source[m["source_query_id"]]
        if (case["query"] != original["query"]
                or m["source_group_id"] != original["source_group_id"]
                or m["pair_id"] != original["pair_id"]
                or m["official_preferred_chunk_id"] != original["preferred_chunk_id"]
                or set(m["display_mapping"]) != {"X", "Y"}
                or set(m["display_mapping"].values()) != {
                    original["preferred_chunk_id"], original["other_chunk_id"]}):
            raise ReviewHandoffError("private identity or query mismatch")
        if [p.get("display_id") for p in case["paragraphs"]] != ["X", "Y"]:
            raise ReviewHandoffError("paragraph order mismatch")
        for p in case["paragraphs"]:
            cid = m["display_mapping"][p["display_id"]]
            if (set(p) != {"display_id", "content"}
                    or p["content"] != bodies[cid]["content"]
                    or not isinstance(p["content"], str)
                    or m["present_in_query_pool"][cid] != (cid in original["contents"])):
                raise ReviewHandoffError("body or pool-presence mismatch")
        expected_form = {
            "case_id": case["case_id"], "reviewer_name": None, "reviewer_type": None,
            "query_ambiguity": None, "pair_preference": None, "pair_reason": "",
            "adjudication_status": "待复核",
            "paragraphs": [{"display_id": side, "applicability": None,
                            "evidence_spans": [], "reason": ""} for side in ("X", "Y")],
        }
        if form != expected_form:
            raise ReviewHandoffError("template has unexpected fields or existing answers; preserve it")
    html = (folder / "review.html").read_text(encoding="utf-8")
    if html != _review_html(reviewer, cases):
        raise ReviewHandoffError("HTML differs from audited standalone renderer; inspect before copying")
    payload = json.loads(re.search(
        r'<script[^>]*id="review-data"[^>]*>(.*?)</script>', html, re.DOTALL,
    ).group(1))
    if payload["cases"] != cases or payload["packet"] != reviewer:
        raise ReviewHandoffError("embedded cases/packet mismatch")
    forbidden_values = {
        value for row in mapping_rows
        for value in (row["source_query_id"], row["source_group_id"], row["pair_id"],
                      *row["display_mapping"].values())
    }
    for name in PUBLIC_FILES:
        content = (folder / name).read_text(encoding="utf-8")
        if any(value in content for value in forbidden_values):
            raise ReviewHandoffError("private identifier in public content")
    return {"queries": len(cases), "pairs": len({m["pair_id"] for m in mapping_rows}),
            "source_groups": len({m["source_group_id"] for m in mapping_rows}),
            "body_count": sum(len(c["paragraphs"]) for c in cases),
            "html_embedded_cases_exact": True, "private_identity_exact": True,
            "original_order_preserved": True, "public_allowlist_passed": True,
            "mapping_path": str(mapping_path.resolve()),
            "mapping_sha256": file_sha256(mapping_path),
            "source_files": {name: file_sha256(folder / name) for name in PUBLIC_FILES}}


def create_handoff(source: Path, prepared: list[dict], bodies: dict, out: Path) -> dict:
    if out.exists():
        raise ReviewHandoffError(f"refuse to overwrite handoff: {out}")
    verified = {name: validate_existing_packet(
        source / name, source / "private" / f"{name}-mapping.jsonl", name, prepared, bodies,
    ) for name in REVIEWERS}
    first, second = (read_rows(source / name / "cases.jsonl") for name in REVIEWERS)
    if {r["case_id"] for r in first} & {r["case_id"] for r in second}:
        raise ReviewHandoffError("reviewer case identifiers are not isolated")
    out.mkdir(parents=True)
    packages = {}
    for name in REVIEWERS:
        destination = out / name
        destination.mkdir()
        for filename in PUBLIC_FILES:
            shutil.copyfile(source / name / filename, destination / filename)
        (destination / "README.md").write_text(NEUTRAL_INSTRUCTIONS, encoding="utf-8")
        expected = {f"{name}/{filename}" for filename in (*PUBLIC_FILES, "README.md")}
        archive = out / f"{name}_package.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
            for filename in (*PUBLIC_FILES, "README.md"):
                package.write(destination / filename, f"{name}/{filename}")
        with zipfile.ZipFile(archive) as package:
            if set(package.namelist()) != expected or package.testzip() is not None:
                raise ReviewHandoffError("archive members or CRC mismatch")
            for filename in (*PUBLIC_FILES, "README.md"):
                if package.read(f"{name}/{filename}") != (destination / filename).read_bytes():
                    raise ReviewHandoffError("archive bytes mismatch")
        packages[name] = {**verified[name], "zip_path": str(archive.resolve()),
                          "zip_sha256": file_sha256(archive),
                          "distribution_files": {f: file_sha256(destination / f)
                                                 for f in (*PUBLIC_FILES, "README.md")}}
    manifest = {"created_at": datetime.now(UTC).isoformat(), "schema_version": 1,
                "source_review": str(source.resolve()), "resampling": False,
                "renumbering": False, "human_submissions_received": 0,
                "adjudication_status": "pending", "packages": packages,
                "browser_acceptance": "pending", "synthetic_qa_is_not_human_submission": True}
    (out / "handoff-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate_submission(payload: dict, cases: list[dict], reviewer: str,
                        *, expected_schema_version: int | None = None) -> dict:
    """Mechanical intake only. Same choices are not adjudicated human truth."""
    expected = unique(cases, "case_id")
    errors, incomplete, normalized = [], [], []
    if not isinstance(payload, dict):
        return {"errors": ["export must be an object"], "complete": False, "normalized": []}
    version = payload.get("schema_version")
    if (type(version) is not int or version not in (1, 2) or payload.get("packet") != reviewer
            or payload.get("scheduled_cases") != len(cases)):
        errors.append("export schema/packet/count mismatch")
    if expected_schema_version is not None and version != expected_schema_version:
        errors.append("distribution answer schema mismatch; import the old draft into the assigned page and complete new fields")
    # The durable page exports the original renderer's content-bound storage key.
    expected_key = "nevir-human-review-" + hashlib.sha256(
        json.dumps([reviewer, cases], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if version == 2:
        expected_key += STORAGE_SUFFIX
        if payload.get("reason_schema_version") != REASON_SCHEMA_VERSION or payload.get("storage_key") != expected_key:
            errors.append("structured reason/body version mismatch")
    if "storage_key" in payload and payload["storage_key"] != expected_key:
        errors.append("export body version/storage key mismatch")
    identity = payload.get("reviewer_name")
    if not isinstance(identity, str) or not identity.strip() or payload.get("reviewer_type") != "human":
        errors.append("human reviewer identity/type missing; AI output cannot be human gold")
    if not isinstance(payload.get("exported_at"), str):
        errors.append("export timestamp missing")
    else:
        try:
            datetime.fromisoformat(payload["exported_at"])
        except ValueError:
            errors.append("export timestamp invalid")
    answers = payload.get("answers")
    if not isinstance(answers, list):
        errors.append("answers must be a list")
        answers = []
    seen = set()
    for answer in answers:
        if not isinstance(answer, dict):
            errors.append("answer must be an object")
            continue
        cid = answer.get("case_id")
        if not isinstance(cid, str) or cid in seen or cid not in expected:
            errors.append("duplicate/unknown anonymous case ID")
            continue
        seen.add(cid)
        case = expected[cid]
        row_errors, missing = [], []
        if answer.get("reviewer_name") != identity or answer.get("reviewer_type") != "human":
            row_errors.append("row reviewer identity/type differs")
        enums = {"query_ambiguity": {"no", "yes", "uncertain"},
                 "pair_preference": {"X", "Y", "tie", "undetermined"},
                 "adjudication_status": {"待复核", "独立复核", "争议保留"}}
        for key, allowed in enums.items():
            value = answer.get(key)
            if value is None or value == "":
                missing.append(key)
            elif not isinstance(value, str) or value not in allowed:
                row_errors.append(f"invalid {key}")
        if answer.get("adjudication_status") == "待复核":
            missing.append("unreviewed")
        if version == 2 and not isinstance(answer.get("pair_reason"), str):
            row_errors.append("invalid pair_reason")
        elif version != 2 and (not isinstance(answer.get("pair_reason"), str) or not answer["pair_reason"].strip()):
            missing.append("pair_reason")
        paragraphs = answer.get("paragraphs")
        if (not isinstance(paragraphs, list) or len(paragraphs) != 2
                or any(not isinstance(p, dict) for p in paragraphs)
                or [p.get("display_id") for p in paragraphs] != ["X", "Y"]):
            row_errors.append("paragraph identities/order mismatch")
            paragraphs = []
        for p, original in zip(paragraphs, case["paragraphs"], strict=False):
            side = p["display_id"]
            value = p.get("applicability")
            if value is None or value == "":
                missing.append(f"{side}.applicability")
            elif not isinstance(value, str) or value not in {"支持所问条件", "明确不满足必要条件", "相关但证据不足", "无法裁定"}:
                row_errors.append(f"invalid {side}.applicability")
            if version == 2 and not isinstance(p.get("reason"), str):
                row_errors.append(f"invalid {side}.reason")
            elif version != 2 and (not isinstance(p.get("reason"), str) or not p["reason"].strip()):
                missing.append(f"{side}.reason")
            spans = p.get("evidence_spans")
            if not isinstance(spans, list):
                row_errors.append(f"invalid {side}.evidence_spans")
                spans = []
            if version != 2 and isinstance(value, str) and value in {"支持所问条件", "明确不满足必要条件"} and not spans:
                missing.append(f"{side}.evidence")
            for span in spans:
                if (not isinstance(span, dict) or type(span.get("start")) is not int
                        or type(span.get("end")) is not int
                        or not 0 <= span["start"] < span["end"] <= len(original["content"])
                        or original["content"][span["start"]:span["end"]] != span.get("quote")):
                    row_errors.append(f"{side}.Unicode evidence mismatch")
        if version == 2 and not row_errors:
            row_errors.extend(structured_errors(answer))
            if not row_errors:
                missing.extend(structured_missing(answer))
        elif version == 1 and ("answer_schema_version" in answer or "pair_reason_code" in answer
                               or any("reason_types" in p for p in paragraphs)):
            row_errors.append("structured fields mixed into legacy schema")
        errors.extend(f"{cid}: {error}" for error in row_errors)
        if missing:
            incomplete.append({"case_id": cid, "missing": missing})
        normalized.append({**answer, "technical_errors": row_errors, "missing": missing,
                           "human_adjudication": "pending"})
    missing_ids = [c["case_id"] for c in cases if c["case_id"] not in seen]
    return {"errors": errors, "missing_case_ids": missing_ids, "incomplete_cases": incomplete,
            "submitted_cases": len(seen), "complete": not errors and not incomplete and not missing_ids,
            "reviewer_name": identity, "reviewer_type": payload.get("reviewer_type"),
            "answer_schema_version": version,
            "reason_schema_version": payload.get("reason_schema_version"),
            "validation_policy_version": VALIDATION_POLICY_VERSION if version == 2 else "legacy_v1",
            "export_completion_policy": "recomputed from original answers; exporter completion summary is not authoritative",
            "reason_selection_counts": {
                "paragraphs": {k: sum(k in p.get("reason_types", []) for a in normalized if not a["technical_errors"]
                                      for p in a["paragraphs"]) for k in REASON_TYPES},
                "pairs": {k: sum(a.get("pair_reason_code") == k for a in normalized if not a["technical_errors"])
                          for k in PAIR_REASON_CODES},
                "interpretation": "descriptive human selections only; multiple choices; no semantic adjudication",
            } if version == 2 else None,
            "normalized": normalized, "human_adjudication": "pending",
            "version_check": ("content-bound storage key and distributed packet verified"
                              if payload.get("storage_key") == expected_key else
                              "legacy export: IDs verified; no embedded content-bound storage key")}


def receive_submission(submission: Path, handoff_manifest: Path, reviewer: str, out: Path) -> dict:
    """Preserve exact original bytes before validating; each invocation needs a new version directory."""
    if reviewer not in REVIEWERS or out.exists():
        raise ReviewHandoffError("unknown reviewer or intake directory already exists")
    manifest = json.loads(handoff_manifest.read_text())
    package = manifest["packages"][reviewer]
    folder = handoff_manifest.parent / reviewer
    for name, expected in package["distribution_files"].items():
        if file_sha256(folder / name) != expected:
            raise ReviewHandoffError("distributed packet changed")
    mapping = Path(package["mapping_path"])
    if file_sha256(mapping) != package["mapping_sha256"]:
        raise ReviewHandoffError("original private mapping changed")
    out.mkdir(parents=True)
    original = out / "original-submission.json"
    original.write_bytes(submission.read_bytes())
    original.chmod(0o444)
    receipt = {"received_at": datetime.now(UTC).isoformat(), "source_filename": submission.name,
               "original_sha256": file_sha256(original), "original_path": str(original.resolve()),
               "reviewer_packet": reviewer, "distribution_zip_sha256": package["zip_sha256"],
               "previous_version_policy": "new explicit directory per submission; never silently select final"}
    try:
        payload = json.loads(original.read_text())
        result = validate_submission(payload, read_rows(folder / "cases.jsonl"), reviewer,
                                     expected_schema_version=manifest.get("answer_schema_version", 1))
    except (ValueError, UnicodeDecodeError) as error:
        result = {"errors": [f"invalid JSON export: {type(error).__name__}"], "complete": False,
                  "normalized": [], "human_adjudication": "pending"}
    receipt.update({k: v for k, v in result.items() if k != "normalized"})
    (out / "normalized.json").write_text(json.dumps(result["normalized"], ensure_ascii=False, indent=2) + "\n")
    receipt["normalized_sha256"] = file_sha256(out / "normalized.json")
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def disagreement_material(handoff_manifest: Path, first: Path, second: Path, out: Path) -> dict:
    """Align through original private mapping. Export neutral human-only adjudication material."""
    if out.exists():
        raise ReviewHandoffError("refuse to overwrite adjudication material")
    manifest = json.loads(handoff_manifest.read_text())
    records = {}
    names = []
    for reviewer, intake in zip(REVIEWERS, (first, second), strict=True):
        receipt = json.loads((intake / "receipt.json").read_text())
        if receipt["reviewer_packet"] != reviewer or receipt.get("errors"):
            raise ReviewHandoffError("resolve intake identity/format errors before association")
        if receipt.get("reviewer_type") != "human":
            raise ReviewHandoffError("two independent humans required")
        if (file_sha256(intake / "original-submission.json") != receipt["original_sha256"]
                or file_sha256(intake / "normalized.json") != receipt["normalized_sha256"]):
            raise ReviewHandoffError("original/normalized human submission changed")
        names.append(receipt["reviewer_name"])
        package = manifest["packages"][reviewer]
        if receipt.get("distribution_zip_sha256") != package["zip_sha256"]:
            raise ReviewHandoffError("intake belongs to another distribution; use its saved manifest")
        for filename, expected in package["distribution_files"].items():
            if file_sha256(handoff_manifest.parent / reviewer / filename) != expected:
                raise ReviewHandoffError("distributed packet changed")
        mapping = Path(package["mapping_path"])
        if file_sha256(mapping) != package["mapping_sha256"]:
            raise ReviewHandoffError("private mapping changed")
        cases = unique(read_rows(handoff_manifest.parent / reviewer / "cases.jsonl"), "case_id")
        answers = unique(json.loads((intake / "normalized.json").read_text()), "case_id")
        records[reviewer] = {r["source_query_id"]: (r, cases[r["case_id"]], answers.get(r["case_id"]))
                             for r in read_rows(mapping)}
    if names[0] == names[1]:
        raise ReviewHandoffError("reviewer identities must be distinct")
    rows = []
    for qid, (left_map, case, left) in records["reviewer_1"].items():
        right_map, right_case, right = records["reviewer_2"][qid]
        if case["query"] != right_case["query"]:
            raise ReviewHandoffError("mapped queries differ")
        neutral = []
        for mapping, public, answer in ((left_map, case, left), (right_map, right_case, right)):
            if answer is None:
                neutral.append(None)
                continue
            destination = {cid: side for side, cid in left_map["display_mapping"].items()}
            translations = {side: destination[cid] for side, cid in mapping["display_mapping"].items()}
            for paragraph in public["paragraphs"]:
                canonical_side = translations[paragraph["display_id"]]
                if paragraph["content"] != next(p["content"] for p in case["paragraphs"] if p["display_id"] == canonical_side):
                    raise ReviewHandoffError("mapped body differs")
            neutral.append({"reviewer_name": answer["reviewer_name"], "query_ambiguity": answer.get("query_ambiguity"),
                            "original_case_id": answer["case_id"],
                            "original_to_canonical_display": translations,
                            "original_pair_preference": answer.get("pair_preference"),
                            "reason_display_convention": "原始理由中的 X/Y 保留该审阅者原显示标识；按 original_to_canonical_display 对照正文。",
                            "pair_preference": translations.get(answer.get("pair_preference"), answer.get("pair_preference")),
                            "pair_reason": answer.get("pair_reason", ""), "adjudication_status": answer.get("adjudication_status"),
                            "answer_schema_version": answer.get("answer_schema_version", 1),
                            "pair_reason_code": answer.get("pair_reason_code"),
                            "paragraphs": sorted([{**p, "display_id": translations[p["display_id"]],
                                                   "original_display_id": p["display_id"]}
                                                  for p in answer["paragraphs"]], key=lambda p: p["display_id"]),
                            "incomplete": bool(answer["missing"])})
        reasons = comparison_flags(neutral)
        rows.append({**case, "human_reviews": neutral, "mechanical_flags": reasons,
                     "rationale_consistency": "requires human check even when choices agree",
                     "adjudication": {"status": "pending", "adjudicator": None, "time": None,
                                      "version": None, "pair_preference": None, "reason": ""}})
    out.mkdir(parents=True)
    (out / "human-adjudication-cases.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    (out / "disagreements.json").write_text(json.dumps([r for r in rows if r["mechanical_flags"]], ensure_ascii=False, indent=2) + "\n")
    summary = {"aligned_cases": len(rows), "flagged_cases": sum(bool(r["mechanical_flags"]) for r in rows),
               "classification_version": "independent_available_fields_v2",
               "human_judgments_locked": False, "models_associated": False,
               "rationale_consistency": "not automatically adjudicated; human check required"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def comparison_flags(reviews: list[dict | None]) -> list[str]:
    """Missing fields do not hide other judgments; flags never adjudicate relevance."""
    flags = []
    present = [r for r in reviews if r is not None]
    if len(present) != 2 or any(r["incomplete"] for r in present):
        flags.append("missing_or_incomplete_human_review")
    if len(present) == 2:
        a, b = present

        def differs(left, right):
            return bool(left) and bool(right) and left != right

        if (any(differs(a.get(k), b.get(k)) for k in ("query_ambiguity", "pair_preference"))
                or any(differs(p.get("applicability"), q.get("applicability"))
                       for p, q in zip(a["paragraphs"], b["paragraphs"], strict=True))):
            flags.append("human_choices_disagree")
        if differs(a.get("adjudication_status"), b.get("adjudication_status")):
            flags.append("review_status_differs")
        if (differs(a.get("pair_reason_code"), b.get("pair_reason_code"))
                or any(differs(set(p.get("reason_types", [])), set(q.get("reason_types", [])))
                       for p, q in zip(a["paragraphs"], b["paragraphs"], strict=True))):
            flags.append("human_reason_categories_differ")
    if any(r.get("query_ambiguity") in {"yes", "uncertain"}
           or r.get("pair_preference") == "undetermined"
           or any(p.get("applicability") == "无法裁定" for p in r["paragraphs"])
           or r.get("adjudication_status") == "争议保留" for r in present):
        flags.append("uncertainty_or_ambiguity_retained")
    if any(r.get("pair_preference") == "tie" for r in present):
        flags.append("tie_preference_present")
    return flags
