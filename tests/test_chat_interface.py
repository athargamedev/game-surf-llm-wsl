#!/usr/bin/env python
"""Test suite for the Game_Surf chat interface using Playwright."""

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from playwright.async_api import async_playwright, expect, Page
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8080"
CHAT_URL = f"{BASE_URL}/chat_interface.html"


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


async def log(msg: str):
    print(f"  {msg}")


class ChatInterfaceTester:
    def __init__(self):
        self.results: list[TestResult] = []
        self.page: Page = None

    async def setup(self):
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        self.page = await context.new_page()
        await self.page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15000)

    async def teardown(self):
        if self.page:
            await self.page.context.browser.close()

    async def test_page_loads(self) -> TestResult:
        await log("Testing page loads...")
        try:
            title = await self.page.title()
            if "Game_Surf" in title:
                return TestResult(True, "Page loads", {"title": title})
            return TestResult(False, f"Wrong title: {title}")
        except Exception as e:
            return TestResult(False, f"Load error: {e}")

    async def test_npc_selector_exists(self) -> TestResult:
        await log("Testing NPC selector...")
        try:
            npc_options = await self.page.locator(".npc-option").count()
            if npc_options > 0:
                return TestResult(True, f"Found {npc_options} NPCs", {"count": npc_options})
            return TestResult(False, "No NPCs found")
        except Exception as e:
            return TestResult(False, f"Selector error: {e}")

    async def test_npc_selection_works(self) -> TestResult:
        await log("Testing NPC selection...")
        try:
            await self.page.locator('.npc-option[data-npc="kosmos_instructor"]').click()
            await self.page.wait_for_timeout(500)

            active = await self.page.locator('.npc-option.active').text_content()
            if "Greek Mythology" in active:
                return TestResult(True, "NPC selection works", {"selected": active.strip()})
            return TestResult(False, f"Selection failed: {active}")
        except Exception as e:
            return TestResult(False, f"Selection error: {e}")

    async def test_player_name_input(self) -> TestResult:
        await log("Testing player name input...")
        try:
            input_box = self.page.locator("#playerNameInput")
            await input_box.fill("TestPlayer")

            set_btn = self.page.locator("button:has-text('Set Player Name')")
            await set_btn.click()
            await self.page.wait_for_timeout(500)

            display = await self.page.locator("#currentPlayerDisplay").text_content()
            if "TestPlayer" in display:
                return TestResult(True, "Player name set", {"name": display.strip()})
            return TestResult(False, f"Name not set: {display}")
        except Exception as e:
            return TestResult(False, f"Input error: {e}")

    async def test_chat_input_exists(self) -> TestResult:
        await log("Testing chat input...")
        try:
            chat_input = self.page.locator("#chatInput")
            is_visible = await chat_input.is_visible()
            if is_visible:
                return TestResult(True, "Chat input visible")
            return TestResult(False, "Chat input not visible")
        except Exception as e:
            return TestResult(False, f"Input error: {e}")

    async def test_send_button(self) -> TestResult:
        await log("Testing send button...")
        try:
            send_btn = self.page.locator("#sendBtn")
            is_visible = await send_btn.is_visible()
            if is_visible:
                return TestResult(True, "Send button visible")
            return TestResult(False, "Send button not visible")
        except Exception as e:
            return TestResult(False, f"Button error: {e}")

    async def test_status_card(self) -> TestResult:
        await log("Testing status card...")
        try:
            status_card = self.page.locator("#statusCard")
            is_visible = await status_card.is_visible()
            if is_visible:
                text = await status_card.text_content()
                return TestResult(True, "Status card visible", {"status": text.strip()[:50]})
            return TestResult(False, "Status card not visible")
        except Exception as e:
            return TestResult(False, f"Status error: {e}")

    async def test_npc_buttons_match_config(self) -> TestResult:
        await log("Testing NPC buttons match config...")
        try:
            config_path = Path("/root/Game_Surf/Tools/LLM_WSL/datasets/configs/npc_profiles.json")
            if not config_path.exists():
                return TestResult(False, "No config file")

            config = json.loads(config_path.read_text())
            config_npcs = set(config.get("profiles", {}).keys())

            page_npcs = await self.page.locator(".npc-option").all()
            page_npc_ids = []
            for npc in page_npcs:
                id_val = await npc.get_attribute("data-npc")
                if id_val:
                    page_npc_ids.append(id_val)

            missing = config_npcs - set(page_npc_ids)
            extra = set(page_npc_ids) - config_npcs

            if not missing and not extra:
                return TestResult(True, "NPCs match config", {"count": len(page_npc_ids)})
            else:
                return TestResult(
                    False,
                    "NPC mismatch",
                    {"missing": list(missing), "extra": list(extra)}
                )
        except Exception as e:
            return TestResult(False, f"Config check error: {e}")

    async def test_clear_chat_button(self) -> TestResult:
        await log("Testing clear chat button...")
        try:
            clear_btn = self.page.locator("button:has-text('Clear Chat')")
            is_visible = await clear_btn.is_visible()
            if is_visible:
                return TestResult(True, "Clear button visible")
            return TestResult(False, "Clear button not visible")
        except Exception as e:
            return TestResult(False, f"Clear error: {e}")

    async def test_reset_runtime_button(self) -> TestResult:
        await log("Testing reset runtime button...")
        try:
            reset_btn = self.page.locator("button:has-text('Reset Runtime Cache')")
            is_visible = await reset_btn.is_visible()
            if is_visible:
                return TestResult(True, "Reset button visible")
            return TestResult(False, "Reset button not visible")
        except Exception as e:
            return TestResult(False, f"Reset error: {e}")

    async def test_message_container(self) -> TestResult:
        await log("Testing message container...")
        try:
            container = self.page.locator("#messageContainer")
            is_visible = await container.is_visible()
            if is_visible:
                return TestResult(True, "Message container visible")
            return TestResult(False, "Container not visible")
        except Exception as e:
            return TestResult(False, f"Container error: {e}")

    async def test_dataset_info_panel(self) -> TestResult:
        await log("Testing dataset info panel...")
        try:
            dataset_info = self.page.locator(".dataset-info")
            is_visible = await dataset_info.first.is_visible()
            if is_visible:
                text = await dataset_info.first.text_content()
                return TestResult(True, "Dataset info visible", {"info": text.strip()[:50]})
            return TestResult(False, "Dataset info not visible")
        except Exception as e:
            return TestResult(False, f"Info error: {e}")

    async def test_api_base_configured(self) -> TestResult:
        await log("Testing API base configured...")
        try:
            api_base = await self.page.evaluate("typeof API_BASE !== 'undefined' ? API_BASE : null")
            if api_base:
                return TestResult(True, "API configured", {"base": api_base})
            return TestResult(False, "API_BASE not defined")
        except Exception as e:
            return TestResult(False, f"API check error: {e}")

    async def test_npc_names_mapping(self) -> TestResult:
        await log("Testing npcNames mapping...")
        try:
            npc_names = await self.page.evaluate("typeof npcNames !== 'undefined' ? npcNames : {}")
            if npc_names and len(npc_names) > 0:
                return TestResult(True, f"Found {len(npc_names)} mappings", {"count": len(npc_names)})
            return TestResult(False, "No npcNames mapping")
        except Exception as e:
            return TestResult(False, f"Mapping error: {e}")

    async def run_all(self):
        print("=" * 60)
        print("Game_Surf Chat Interface Test Suite (Playwright)")
        print("=" * 60)

        await self.setup()

        tests = [
            ("Page Loads", self.test_page_loads),
            ("NPC Selector Exists", self.test_npc_selector_exists),
            ("NPC Selection Works", self.test_npc_selection_works),
            ("Player Name Input", self.test_player_name_input),
            ("Chat Input Exists", self.test_chat_input_exists),
            ("Send Button", self.test_send_button),
            ("Status Card", self.test_status_card),
            ("Clear Chat Button", self.test_clear_chat_button),
            ("Reset Runtime Button", self.test_reset_runtime_button),
            ("Message Container", self.test_message_container),
            ("Dataset Info Panel", self.test_dataset_info_panel),
            ("API Base Configured", self.test_api_base_configured),
            ("NPC Names Mapping", self.test_npc_names_mapping),
            ("NPC Config Match", self.test_npc_buttons_match_config),
        ]

        for name, test_fn in tests:
            try:
                result = await test_fn()
                icon = "✓" if result.passed else "✗"
                print(f"  [{icon}] {name}: {result.message}")
                self.results.append(result)
            except Exception as e:
                print(f"  [✗] {name}: EXCEPTION - {e}")
                self.results.append(TestResult(name, False, str(e)))

        await self.teardown()

        print("\n" + "=" * 60)
        print("Results Summary")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        total = len(self.results)

        print(f"  Total: {total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")

        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        print()
        return failed == 0


async def main():
    tester = ChatInterfaceTester()
    success = await tester.run_all()
    await tester.teardown()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())