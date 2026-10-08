"""Optional UI QA with already-installed Playwright. No downloads or installations.
Run while the local preview is running: python3 tests/browser_check.py
"""
import argparse
import json
import re
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=Path("output/playwright"))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    report = {"url": args.url.rstrip("/"), "browser": "installed Playwright Chromium",
              "checks": [], "console_errors": [], "console_warnings": [], "network_failures": []}
    def checked(name, evidence):
        report["checks"].append({"name": name, "status": "PASS", "evidence": evidence})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: report["console_errors"].append(str(error)))
        page.on("console", lambda message: report["console_errors" if message.type == "error" else "console_warnings"].append(message.text) if message.type in ("error", "warning") else None)
        page.on("requestfailed", lambda request: report["network_failures"].append(request.url))
        page.goto(report["url"], wait_until="networkidle")
        expect(page).to_have_title("community AI Compute · 本機工作台")
        expect(page.get_by_role("heading", name=re.compile(r"讓閒置資源，\s*完成有用工作。"))).to_be_visible()
        expect(page.locator("#metric-nodes")).to_have_text("3")
        checked("page_identity_and_meaningful_content", {"title": page.title(), "url": page.url})

        if page.get_by_role("button", name="恢復貢獻", exact=True).count():
            page.get_by_role("button", name="恢復貢獻", exact=True).click()
        page.locator("#usage").select_option("idle")
        page.locator("#foreground").uncheck()
        page.locator("#consent").check()
        page.locator("[name=mode][value=manual]").check()
        page.locator("#budget").focus()
        page.locator("#budget").press("Home")
        for _ in range(11):
            page.locator("#budget").press("ArrowRight")
        page.get_by_role("button", name="套用設定", exact=True).click()
        expect(page.locator("#effective")).to_have_text("60%")
        page.locator("#count").fill("384")
        with page.expect_response(lambda response: response.url == report["url"] + "/api/jobs" and response.request.method == "POST") as submitted:
            page.get_by_role("button", name="提交批次", exact=True).click()
        jid = submitted.value.json()["job_id"]
        job_row = page.locator("#jobs tr").filter(has_text=jid)
        expect(job_row.locator(".state")).to_have_text("已完成", timeout=20000)
        href = job_row.get_by_role("link", name="取回 JSON").get_attribute("href")
        result = page.request.get(report["url"] + href).json()
        assert len(result["results"]) == 384
        checked("customer_submit_to_verified_output", {"job_id": result["job_id"], "images": 384})

        page.locator("#count").fill("4096")
        page.locator("#batch").select_option("64")
        with page.expect_response(lambda response: response.url == report["url"] + "/api/jobs" and response.request.method == "POST") as submitted_long:
            page.get_by_role("button", name="提交批次", exact=True).click()
        long_id = submitted_long.value.json()["job_id"]
        long_row = page.locator("#jobs tr").filter(has_text=long_id)
        expect(long_row.locator(".state")).to_have_text("進行中", timeout=10000)
        page.get_by_role("button", name="暫停貢獻", exact=True).click()
        expect(page.locator("#effective")).to_have_text("0%")
        time.sleep(.35)
        a = page.request.get(report["url"] + "/api/state").json()["totals"]["credits"]
        time.sleep(.35)
        b = page.request.get(report["url"] + "/api/state").json()["totals"]["credits"]
        assert a == b, (a, b)
        checked("pause_during_active_job", {"credits_stable": a, "observed_seconds": .35})

        page.locator("#foreground").check()
        page.get_by_role("button", name="套用設定", exact=True).click()
        page.get_by_role("button", name="恢復貢獻", exact=True).click()
        expect(page.locator("#effective")).to_have_text("0%")
        page.locator("#usage").select_option("coexist")
        page.get_by_role("button", name="套用設定", exact=True).click()
        expect(page.locator("#effective")).to_have_text("15%")
        checked("simulated_foreground_policy", "idle: 0%; coexist: at most 15%; explicitly simulated")
        page.locator("#foreground").uncheck()
        page.get_by_role("button", name="套用設定", exact=True).click()
        expect(long_row.locator(".state")).to_have_text("已完成", timeout=30000)

        row = page.locator("#nodes tr").filter(has_text="cpu-3")
        old = row.locator("small").inner_text()
        row.get_by_role("button", name="停止程序").click()
        expect(row.locator(".state")).to_have_text("已停止")
        row.get_by_role("button", name="啟動程序").click()
        expect(row.locator(".state")).to_have_text("就緒")
        new = row.locator("small").inner_text()
        assert old != new
        checked("stop_and_restart_real_process", {"old": old, "new": new})

        page.get_by_role("button", name="API", exact=True).click()
        expect(page.get_by_role("heading", name="從一個批次 API 開始。", exact=True)).to_be_visible()
        assert "Idempotency-Key" in page.locator("#api-example").inner_text()
        page.get_by_role("button", name="開源方向", exact=True).click()
        expect(page.get_by_role("heading", name="開放協議，從可信成果開始。", exact=True)).to_be_visible()
        checked("api_and_adoption_navigation", "Both panels rendered with working navigation")
        page.get_by_role("button", name="工作台", exact=True).click()
        page.locator("#notice").wait_for(state="hidden", timeout=10000)
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        checked("desktop_layout", {"viewport": [1440, 1000], "horizontal_overflow": False})
        page.set_viewport_size({"width": 1505, "height": 1045})
        page.screenshot(path=str(output / "desktop-native.png"), full_page=True)
        checked("concept_native_viewport", {"viewport": [1505, 1045]})
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("h1").first).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        page.locator("#pause").click()
        expect(page.locator("#pause")).to_have_text("恢復貢獻")
        checked("mobile_layout_and_control", {"viewport": [390, 844], "horizontal_overflow": False, "pause_button": "responded"})
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("#consent").uncheck()
        page.get_by_role("button", name="套用設定", exact=True).click()
        expect(page.locator("#effective")).to_have_text("0%")
        assert not report["console_errors"], report["console_errors"]
        assert not report["console_warnings"], report["console_warnings"]
        assert not report["network_failures"], report["network_failures"]
        checked("console_and_network", "No console errors, warnings, failed requests or framework overlay")
        report["final_state"] = page.request.get(report["url"] + "/api/state").json()["totals"]
        browser.close()
    (output / "ui-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
