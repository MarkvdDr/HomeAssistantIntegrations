"""Consistency checks for the packaged integration.

These tests do not need Home Assistant: they verify the metadata, the
translations and the files that make the component installable.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "toon_program"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def key_tree(value: object) -> object:
    """Return the nested key structure of a translation file."""
    if isinstance(value, dict):
        return {key: key_tree(item) for key, item in value.items()}
    return None


class ManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load(COMPONENT / "manifest.json")

    def test_required_fields(self) -> None:
        for key in (
            "domain",
            "name",
            "codeowners",
            "config_flow",
            "documentation",
            "iot_class",
            "issue_tracker",
            "version",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.manifest)

        self.assertEqual(self.manifest["domain"], "toon_program")
        self.assertTrue(self.manifest["config_flow"])
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_links_point_to_this_repository(self) -> None:
        self.assertEqual(
            self.manifest["documentation"],
            "https://github.com/MarkvdDr/HomeAssistantIntegrations",
        )
        self.assertEqual(
            self.manifest["issue_tracker"],
            "https://github.com/MarkvdDr/HomeAssistantIntegrations/issues",
        )


class HacsTest(unittest.TestCase):
    def test_hacs_manifest(self) -> None:
        hacs = load(ROOT / "hacs.json")
        self.assertEqual(hacs["name"], "Toon Program")
        self.assertRegex(hacs["homeassistant"], r"^\d{4}\.\d+\.\d+$")


class TranslationsTest(unittest.TestCase):
    def test_strings_match_english(self) -> None:
        strings = load(COMPONENT / "strings.json")
        english = load(COMPONENT / "translations" / "en.json")
        self.assertEqual(strings, english)

    def test_dutch_covers_every_english_key(self) -> None:
        english = load(COMPONENT / "translations" / "en.json")
        dutch = load(COMPONENT / "translations" / "nl.json")
        self.assertEqual(key_tree(english), key_tree(dutch))

    def test_services_are_translated(self) -> None:
        expected = {
            "set_schedule",
            "set_day",
            "create_backup",
            "restore_backup",
        }
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = load(COMPONENT / "translations" / f"{language}.json")
                self.assertEqual(set(data["services"]), expected)


class PackagingTest(unittest.TestCase):
    def test_expected_files_exist(self) -> None:
        for relative in (
            "__init__.py",
            "config_flow.py",
            "diagnostics.py",
            "manifest.json",
            "services.yaml",
            "strings.json",
            "frontend/toon-program-card.js",
            "brand/icon.png",
            "brand/logo.png",
            "translations/en.json",
            "translations/nl.json",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((COMPONENT / relative).is_file(), relative)

    def test_no_home_assistant_internals_are_packaged(self) -> None:
        forbidden = {
            ".storage",
            "home-assistant.log",
            "home-assistant_v2.db",
            "secrets.yaml",
            "AGENTS.md",
        }
        found = {
            path.name
            for path in COMPONENT.rglob("*")
            if path.is_file() and path.name in forbidden
        }
        self.assertEqual(found, set())

    def test_card_is_not_truncated(self) -> None:
        card = COMPONENT / "frontend" / "toon-program-card.js"
        text = card.read_text(encoding="utf-8")
        self.assertGreater(len(text), 10_000)
        self.assertIn("customElements.define", text)


if __name__ == "__main__":
    unittest.main()
