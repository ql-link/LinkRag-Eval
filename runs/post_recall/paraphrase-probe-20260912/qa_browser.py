"""Headless offline review UI check; simulated submissions never enter human history."""

import json
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent


def main():
    checks = HERE / "checks"
    checks.mkdir(exist_ok=True)
    errors = []
    with (
        tempfile.TemporaryDirectory(prefix="issue22-ui-synthetic-") as temp,
        sync_playwright() as p,
    ):
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1080}, accept_downloads=True
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((HERE / "review.html").as_uri())
        page.wait_for_load_state("networkidle")
        expect(page.locator("#jump option")).to_have_count(36)
        expect(page.locator("#progress")).to_contain_text("已填写 0/36")
        expect(page.locator("#current .english")).to_have_count(4)
        page.screenshot(path=str(checks / "review-desktop.png"), full_page=True)
        page.locator("#status").select_option("approved")
        page.locator("#export").click()
        expect(page.locator("#message")).to_contain_text("请填写审核人")
        page.locator("#reviewer").fill("AUTOMATED_UI_TEST_NOT_HUMAN")
        page.locator("#date").fill("2026-09-12")
        page.locator("#assistance").select_option(index=2)
        page.locator("#reason").fill("Synthetic UI validation only; not a semantic review.")
        page.locator("#export").click()
        expect(page.locator("#message")).to_contain_text("请确认由本人实际审核")
        for selector in ("#conditions", "#preferences", "#equivalence", "#confirmed"):
            page.locator(selector).check()
        page.locator("#next").click()
        page.locator("#date").fill("2026-09-13")
        page.locator("#prev").click()
        expect(page.locator("#status")).to_have_value("approved")
        page.reload()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#progress")).to_contain_text("已填写 1/36")
        with page.expect_download() as event:
            page.locator("#export").click()
        backup = Path(temp) / "synthetic-download.jsonl"
        event.value.save_as(str(backup))
        rows = [json.loads(line) for line in backup.read_text().splitlines()]
        assert len(rows) == 36 and rows[0]["reviewed_at"] == "2026-09-12"
        assert sum(r["status"] == "pending" for r in rows) == 35
        fresh = browser.new_context(viewport={"width": 390, "height": 844})
        mobile = fresh.new_page()
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto((HERE / "review.html").as_uri())
        mobile.wait_for_load_state("networkidle")
        expect(mobile.locator("#progress")).to_contain_text("已填写 0/36")
        assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
        mobile.screenshot(path=str(checks / "review-mobile.png"), full_page=True)
        mobile.locator("#file").set_input_files(str(backup))
        expect(mobile.locator("#message")).to_contain_text("已导入 36 项记录")
        expect(mobile.locator("#progress")).to_contain_text("已填写 1/36")
        rows[0]["input_digest"] = "STALE-SYNTHETIC-DIGEST"
        bad = Path(temp) / "synthetic-stale.jsonl"
        bad.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        mobile.locator("#file").set_input_files(str(bad))
        expect(mobile.locator("#message")).to_contain_text("导入失败")
        expect(mobile.locator("#progress")).to_contain_text("已填写 1/36")
        fresh.close()
        context.close()
        browser.close()
    assert not errors, errors
    assert (HERE / "human-review.jsonl").read_text() == ""
    result = {
        "status": "passed",
        "page_errors": errors,
        "checks": [
            "36 items / 4 English texts each",
            "approval validation",
            "autosave/reload",
            "original review date survives navigation",
            "JSONL export / clean-context import",
            "stale digest rejected without overwriting imported state",
            "mobile no overflow",
        ],
        "identity": "synthetic browser tests only; no real human decisions or inference",
        "real_human_records": 0,
    }
    (checks / "browser-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
