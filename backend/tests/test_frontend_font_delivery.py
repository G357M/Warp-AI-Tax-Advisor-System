"""Static contract for deterministic, language-aware frontend font delivery."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

EXPECTED_FONTS = {
    "@fontsource/instrument-serif": "5.3.0",
    "@fontsource/barlow": "5.3.0",
    "@fontsource-variable/inter": "5.3.0",
    "@fontsource-variable/noto-sans-georgian": "5.3.0",
    "@fontsource-variable/noto-serif-georgian": "5.3.0",
}


def test_frontend_fonts_are_local_and_exactly_pinned():
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))

    for name, version in EXPECTED_FONTS.items():
        assert package["dependencies"][name] == version
        assert lock["packages"][""]["dependencies"][name] == version

    source_files = [
        path
        for source_root in ("app", "components", "lib")
        for path in (FRONTEND / source_root).rglob("*")
        if path.suffix in {".css", ".js", ".mjs", ".ts", ".tsx"}
    ]
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    assert "next/font/google" not in source_text
    assert "fonts.googleapis" not in source_text
    assert "fonts.gstatic" not in source_text

    layout = (FRONTEND / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "@fontsource-variable/inter/wght.css" in layout
    assert "@fontsource-variable/noto-sans-georgian/wght.css" in layout
    assert "@fontsource-variable/noto-serif-georgian/wght.css" in layout


def test_real_language_fonts_precede_metric_fallbacks():
    tailwind = (FRONTEND / "tailwind.config.ts").read_text(encoding="utf-8")
    globals_css = (FRONTEND / "app" / "globals.css").read_text(encoding="utf-8")

    body_stack = """'var(--font-barlow)',
          'var(--font-inter)',
          'var(--font-georgian)',
          'Inter Fallback',
          'Barlow Fallback'"""
    heading_stack = """'var(--font-instrument)',
          'var(--font-georgian-serif)',
          'Instrument Serif Fallback'"""

    assert tailwind.count(body_stack) == 2
    assert heading_stack in tailwind
    assert "--font-inter: 'Inter Variable';" in globals_css
    assert "--font-georgian: 'Noto Sans Georgian Variable';" in globals_css
    assert "--font-georgian-serif: 'Noto Serif Georgian Variable';" in globals_css
