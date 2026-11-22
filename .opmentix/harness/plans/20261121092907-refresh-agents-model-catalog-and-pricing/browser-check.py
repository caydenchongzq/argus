#!/usr/bin/env python3
"""Settings browser regression against real Argus with a synthetic OpenRouter feed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[4]
ADD_MODEL = "openai/gpt-6.2-astra"
PREVIEW_MODEL = "google/gemini-test-preview"
MALICIOUS_DESCRIPTION = '<img src="/provider-should-not-render" onerror="window.providerHtmlRan=true">'


def provider_model(model_id, name, price, *, output="text", description="Synthetic provider details"):
    return {
        "id": model_id,
        "name": name,
        "description": description,
        "context_length": 256_000,
        "architecture": {"input_modalities": ["text"], "output_modalities": [output]},
        "supported_parameters": ["tools", "tool_choice", "response_format", "structured_outputs", "reasoning"],
        "pricing": {"prompt": price, "completion": "0.000040"},
        "top_provider": {"max_completion_tokens": 16_384},
    }


FEED = {"data": [
    provider_model("openai/gpt-6.1-sol", "OpenAI: GPT-6.1 Sol", "0.0000025"),
    provider_model("openai/gpt-6-luna", "OpenAI: GPT-6 Luna", "0.000000125"),
    provider_model("anthropic/claude-opus-5.5", "Anthropic: Claude Opus 5.5", "0.000004"),
    provider_model(ADD_MODEL, "OpenAI: GPT-6.2 Astra", "0.000008", description=MALICIOUS_DESCRIPTION),
    provider_model(PREVIEW_MODEL, "Google: Gemini Test Preview", "0"),
    provider_model("google/gemini-test-image", "Google: Gemini Image", "0.000002", output="image"),
]}
next(model for model in FEED["data"] if model["id"] == ADD_MODEL)["pricing"]["overrides"] = [
    {"min_prompt_tokens": 272_000, "prompt": "0.000016", "completion": "0.000060"},
]


@contextmanager
def fixture_server(tmp):
    ta = tmp / "TradingAgents"
    shutil.copytree(ROOT.parent / "TradingAgents" / "addons", ta / "addons",
                    ignore=shutil.ignore_patterns("__pycache__", "*.bak*"))
    data = ta / "data"
    data.mkdir()
    (data / "targets.json").write_text('{"weekly_budget_usd": 25, "budget": {"enabled": false}}')
    (data / "my_book.json").write_text('{"cash": 0, "positions": []}')
    (data / "watchlist.json").write_text("[]")
    overrides = tmp / "agent_config.json"
    overrides.write_text('{"seats":{}}')
    inventory = ta / "addons" / "openrouter_models.json"
    seed = json.loads(inventory.read_text())
    seed["fetched_at"] = "2020-01-01T00:00:00Z"
    inventory.write_text(json.dumps(seed))
    feed = tmp / "provider.json"
    feed.write_text(json.dumps(FEED))
    env = {
        **os.environ,
        "TRADINGAGENTS_ROOT": str(ta),
        "ARGUS_ADDONS_DIR": str(ta / "addons"),
        "ARGUS_AGENT_CONFIG": str(overrides),
        "ARGUS_MODELS_CONFIG": str(inventory),
        "DASHBOARD_RUNS_DIR": str(tmp / "runs"),
        "ARGUS_HOST": "127.0.0.1",
    }
    process = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "-u", "-c", """
from datetime import datetime, timezone
from pathlib import Path
import json
import socket
import sys
import uvicorn
import server
import model_inventory

def fixture_fetch(*args, **kwargs):
    feed = json.loads(Path(sys.argv[1]).read_text())
    return model_inventory.normalize_openrouter(feed, fetched_at=datetime.now(timezone.utc).isoformat())

model_inventory.fetch_openrouter = fixture_fetch
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1], flush=True)
    uvicorn.Server(uvicorn.Config(server.app, log_level="error")).run(sockets=[listener])
""", str(feed)], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdout is not None
        port = int(process.stdout.readline().strip())
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(base + "/api/health", timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline or process.poll() is not None:
                    raise
                time.sleep(0.05)
        yield base, feed
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()


def verify(page, base, feed):
    unexpected = []
    errors = []

    def guard(route):
        request = route.request
        path = urlparse(request.url).path
        if not request.url.startswith(base + "/") or (
            path in {"/api/runs", "/api/theme-scout"} and request.method == "POST"
        ) or path == "/provider-should-not-render":
            unexpected.append(request.url)
            route.abort()
        else:
            route.continue_()

    page.route("**/*", guard)
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(base + "/agents", wait_until="domcontentloaded")
    expect(page).to_have_url(base + "/settings")
    expect(page.locator('#nav a[href="/settings"]')).to_have_attribute("aria-current", "page")
    expect(page.locator("#agentTable")).to_contain_text("Theme scout")

    page.locator('[href="/settings/watchlist"]').click()
    expect(page).to_have_url(base + "/settings/watchlist")
    expect(page.locator("#settingsBudgetUsd")).to_have_value("25")
    page.locator("#settingsBudgetUsd").fill("39")
    with page.expect_response(lambda response: response.url.endswith("/api/models/refresh")) as pending:
        page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    assert pending.value.ok, pending.value.text()
    expect(page).to_have_url(base + "/settings/models")
    page.go_back()
    expect(page.locator("#settingsBudgetUsd")).to_have_value("39")
    page.go_forward()
    expect(page.locator("#modelSearch")).to_be_visible()

    search = page.locator("#modelSearch")
    search.focus()
    expect(search).to_be_focused()
    page.keyboard.insert_text(ADD_MODEL)
    results = page.locator("#modelResults")
    expect(results).to_contain_text("GPT-6.2 Astra")
    expect(results).to_contain_text("$8")
    expect(results).to_contain_text("$40")
    expect(results).to_contain_text("256")
    details = results.locator("summary").first
    details.focus()
    page.keyboard.press("Enter")
    expect(results).to_contain_text("272,000")
    expect(results).to_contain_text("$16")
    expect(results).to_contain_text("$60")
    expect(results).to_contain_text(MALICIOUS_DESCRIPTION)
    assert page.evaluate("window.providerHtmlRan") is None
    results.get_by_role("button", name="Add model", exact=True).click()
    saved = page.locator("#savedModels")
    expect(saved).to_contain_text(ADD_MODEL)

    page.reload(wait_until="domcontentloaded")
    expect(saved).to_contain_text(ADD_MODEL)
    busy_catalog_url = "**/api/models?q="

    def remote_refresh_in_progress(route):
        response = route.fetch()
        route.fulfill(response=response, json={**response.json(), "refreshing": True})

    page.route(busy_catalog_url, remote_refresh_in_progress)
    with page.expect_response(lambda response: response.url.endswith("/api/models?q=")):
        page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    page.wait_for_load_state("networkidle")
    expect(page.locator("#modelRefresh")).to_be_enabled()
    page.unroute(busy_catalog_url, remote_refresh_in_progress)
    held_search = []
    slow_url = "**/api/models?q=OpenAI"
    page.route(slow_url, lambda route: held_search.append(route))
    with page.expect_request(lambda request: request.url.endswith("/api/models?q=OpenAI")):
        search.fill("OpenAI")
    search.fill(PREVIEW_MODEL)
    expect(results).to_contain_text("Gemini Test Preview")
    expect(results).to_contain_text("Free")
    with page.expect_response(lambda response: response.url.endswith("/api/models?q=OpenAI")):
        held_search.pop().continue_()
    page.wait_for_load_state("networkidle")
    expect(results).to_contain_text("Gemini Test Preview")
    expect(results).not_to_contain_text("GPT-6.2 Astra")
    with page.expect_response(lambda response: "/api/models?" in response.url
                              and "gemini-test-image" in response.url):
        search.fill("google/gemini-test-image")
    expect(results.get_by_role("button", name="Add model", exact=True)).to_have_count(0)

    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    scout = page.locator('#agentTable [data-seat="theme_scout"]')
    model_pick = scout.locator("[data-model]")
    expect(model_pick.locator(f'option[value="{ADD_MODEL}"]')).to_have_count(1)
    page.locator('#nav a[href="/reports"]').click()
    delayed_agents = []
    agents_url = "**/api/agents"

    def hold_agents(route):
        delayed_agents.append(route)

    page.route(agents_url, hold_agents)
    with page.expect_request(lambda request: request.url.endswith("/api/agents")):
        page.locator('#nav a[href="/settings"]').click()
    model_pick.select_option(ADD_MODEL)
    with page.expect_response(lambda response: response.url.endswith("/api/agents")):
        delayed_agents.pop().continue_()
    page.unroute(agents_url, hold_agents)
    page.wait_for_load_state("networkidle")
    expect(model_pick).to_have_value(ADD_MODEL)
    page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    feed.write_text('{"data":[]}')
    with page.expect_response(lambda response: response.url.endswith("/api/models/refresh")) as pending:
        page.locator("#modelRefresh").click()
    assert pending.value.status >= 400
    expect(saved).to_contain_text(ADD_MODEL)
    expect(page.locator("#modelRefresh")).to_be_enabled()
    feed.write_text(json.dumps(FEED))
    with page.expect_response(lambda response: response.url.endswith("/api/models/refresh")) as pending:
        page.locator("#modelRefresh").click()
    assert pending.value.ok, pending.value.text()
    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    expect(model_pick).to_have_value(ADD_MODEL)

    page.locator("#agentSaveAll").click()
    with page.expect_response(lambda response: response.url.endswith("/api/agents")
                              and response.request.method == "PUT") as pending:
        page.locator("#confirmGo").click()
    assert pending.value.ok, pending.value.text()
    expect(page.locator("#agentDirtyCount")).to_contain_text("No unsaved changes")
    expect(model_pick.locator(f'option[value="{PREVIEW_MODEL}"]')).to_have_count(0)

    page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    added_card = saved.locator("article").filter(has_text=ADD_MODEL)
    expect(added_card).to_contain_text("Theme scout")
    expect(added_card.get_by_role("button", name="In use")).to_be_disabled()
    remaining = [model for model in FEED["data"] if model["id"] != ADD_MODEL]
    feed.write_text(json.dumps({"data": remaining}))
    with page.expect_response(lambda response: response.url.endswith("/api/models/refresh")) as pending:
        page.locator("#modelRefresh").click()
    assert pending.value.ok, pending.value.text()
    expect(added_card).to_contain_text("unavailable")
    expect(added_card).to_contain_text("$8")
    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    pre_save_doc = page.request.get(base + "/api/agents").json()

    def hold_pre_save_read(route):
        if route.request.method == "GET":
            delayed_agents.append(route)
        else:
            route.fallback()

    page.locator('#nav a[href="/reports"]').click()
    page.route(agents_url, hold_pre_save_read)
    with page.expect_request(lambda request: request.url.endswith("/api/agents")):
        page.locator('#nav a[href="/settings"]').click()
    model_pick.select_option("openai/gpt-6.1-sol")
    page.locator("#agentSaveAll").click()
    with page.expect_response(lambda response: response.url.endswith("/api/agents")
                              and response.request.method == "PUT") as pending:
        page.locator("#confirmGo").click()
    assert pending.value.ok, pending.value.text()
    expect(page.locator("#agentDirtyCount")).to_contain_text("No unsaved changes")
    with page.expect_response(lambda response: response.url.endswith("/api/agents")):
        delayed_agents.pop().fulfill(json=pre_save_doc)
    page.unroute(agents_url, hold_pre_save_read)
    page.wait_for_load_state("networkidle")
    expect(model_pick).to_have_value("openai/gpt-6.1-sol")
    page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    added_card.get_by_role("button", name="Remove").click()
    expect(saved).not_to_contain_text(ADD_MODEL)
    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    expect(model_pick.locator(f'option[value="{ADD_MODEL}"]')).to_have_count(0)
    page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    page.reload(wait_until="domcontentloaded")
    expect(saved).not_to_contain_text(ADD_MODEL)

    page.goto(base + "/runs", wait_until="domcontentloaded")
    expect(page.locator("#runSpend")).to_contain_text("weekly check disabled")
    page.locator('#nav a[href="/settings"]').click()
    page.locator('.ar-settings-nav [data-settings-section="watchlist"]').click()
    expect(page.locator("#settingsBudgetUsd")).to_have_value("25")
    page.locator("#settingsBudgetUsd").fill("39")
    page.locator("#settingsBudgetEnabled").check()
    page.locator("#settingsSave").click()
    with page.expect_response(lambda response: response.url.endswith("/api/settings")
                              and response.request.method == "PUT") as pending:
        page.locator("#confirmGo").click()
    assert pending.value.ok, pending.value.text()
    expect(page.locator("#settingsStatus")).to_contain_text("enabled at $39.00")
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("#settingsBudgetUsd")).to_have_value("39")
    expect(page.locator("#settingsBudgetEnabled")).to_be_checked()

    retired = "anthropic/claude-opus-5.5"
    replacement = "openai/gpt-6.1-sol"
    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    assignments = page.request.get(base + "/api/agents").json()["seats"]
    replaced = [seat["id"] for seat in assignments if seat["model"] == retired]
    assert replaced
    for seat_id in replaced:
        page.locator(f'#agentTable [data-seat="{seat_id}"] [data-model]').select_option(replacement)
    page.locator("#agentSaveAll").click()
    with page.expect_response(lambda response: response.url.endswith("/api/agents")
                              and response.request.method == "PUT") as pending:
        page.locator("#confirmGo").click()
    assert pending.value.ok, pending.value.text()
    page.locator('.ar-settings-nav [data-settings-section="models"]').click()
    saved.locator("article").filter(has_text=retired).get_by_role("button", name="Remove").click()
    expect(saved).not_to_contain_text(retired)
    page.locator('.ar-settings-nav [data-settings-section="agents"]').click()
    for seat_id in replaced:
        pick = page.locator(f'#agentTable [data-seat="{seat_id}"] [data-model]')
        expect(pick).to_have_value(replacement)
        expect(pick.locator(f'option[value="{retired}"]')).to_have_count(0)
    page.locator('.ar-settings-nav [data-settings-section="models"]').click()

    page.set_viewport_size({"width": 375, "height": 850})
    for theme in ("light", "dark"):
        page.locator(f'[data-theme-set="{theme}"]').click()
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        expect(search).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), theme

    assert not unexpected, unexpected
    assert not errors, errors


def main():
    with TemporaryDirectory(prefix="argus-settings-browser-") as folder:
        with fixture_server(Path(folder)) as (base, feed), sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = browser.new_page(viewport={"width": 1360, "height": 1000})
                page.set_default_timeout(15_000)
                page.set_default_navigation_timeout(30_000)
                verify(page, base, feed)
            finally:
                browser.close()
    print("Settings browser flow passed")


if __name__ == "__main__":
    main()
