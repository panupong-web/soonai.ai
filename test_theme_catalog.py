import sys

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import ui_theme  # noqa: E402


def test_cli_theme_catalog_contains_complete_presets():
    names = set(ui_theme.theme_names())
    assert {
        "luxe", "aurora", "sunset", "classic",
        "ocean", "forest", "cyberpunk", "mono",
    }.issubset(names)


def test_cli_theme_presets_have_distinct_accents():
    accents = [ui_theme.palette_for(name)["accent"] for name in ui_theme.theme_names()]
    assert len(accents) == len(set(accents))
