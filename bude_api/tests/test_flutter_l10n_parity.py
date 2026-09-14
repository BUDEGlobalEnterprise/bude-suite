"""Localization guards for the four Flutter apps.

The Flutter toolchain is not installed on the development machine, so the
committed `app_localizations*.dart` files are written by `mobile-app/tools/
arb_add.py` rather than by `flutter gen-l10n`. These tests are what keeps that
arrangement honest: every English string must have an Arabic one, and the
generated Dart must actually expose what the ARB files declare.
"""

import json
import re
from pathlib import Path

import pytest

APPS = ["flutter_app", "hr_flutter_app", "helpdesk_flutter_app", "sales_flutter_app"]


def _repo() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "mobile-app").is_dir() and (parent / "backend").is_dir()
    )


def _l10n(app: str) -> Path:
    return _repo() / "mobile-app" / app / "lib" / "l10n"


def _messages(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("@")}


@pytest.mark.parametrize("app", APPS)
def test_every_english_string_has_an_arabic_one(app):
    english = _messages(_l10n(app) / "app_en.arb")
    arabic = _messages(_l10n(app) / "app_ar.arb")

    assert sorted(english) == sorted(arabic), (
        f"{app}: only in en={sorted(set(english) - set(arabic))}, "
        f"only in ar={sorted(set(arabic) - set(english))}"
    )


@pytest.mark.parametrize("app", APPS)
def test_placeholders_match_between_locales(app):
    """A translation that drops a placeholder renders the wrong sentence."""
    english = _messages(_l10n(app) / "app_en.arb")
    arabic = _messages(_l10n(app) / "app_ar.arb")
    simple = re.compile(r"\{(\w+)\}")

    mismatched = {
        key: (sorted(set(simple.findall(value))), sorted(set(simple.findall(arabic[key]))))
        for key, value in english.items()
        # Plural/select messages carry their own nested placeholders.
        if "," not in value and key in arabic
        if set(simple.findall(value)) != set(simple.findall(arabic[key]))
    }

    assert mismatched == {}, f"{app}: {mismatched}"


@pytest.mark.parametrize("app", APPS)
def test_generated_dart_covers_every_arb_key(app):
    """Guards the hand-written codegen: a key with no getter will not compile."""
    keys = set(_messages(_l10n(app) / "app_en.arb"))

    for locale in ("en", "ar"):
        source = (_l10n(app) / f"app_localizations_{locale}.dart").read_text(
            encoding="utf-8"
        )
        declared = set(re.findall(r"String (?:get )?(\w+)[ (=]", source))
        assert keys <= declared, f"{app} ({locale}) missing: {sorted(keys - declared)}"


@pytest.mark.parametrize("app", APPS)
def test_abstract_class_declares_every_arb_key(app):
    keys = set(_messages(_l10n(app) / "app_en.arb"))
    source = (_l10n(app) / "app_localizations.dart").read_text(encoding="utf-8")
    declared = set(re.findall(r"String (?:get )?(\w+)[ (;]", source))

    assert keys <= declared, f"{app} missing: {sorted(keys - declared)}"
