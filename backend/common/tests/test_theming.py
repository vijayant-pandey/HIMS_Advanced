import json
from pathlib import Path

from common.theming import THEMES

FRONTEND_PALETTE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "app" / "themes.json"


def test_admin_themes_match_the_frontend_palette():
    """The admin console and the React apps must offer exactly the same themes and colours."""
    assert json.loads(FRONTEND_PALETTE.read_text(encoding="utf-8")) == THEMES


def test_every_theme_is_white_based_with_readable_primary():
    for theme in THEMES.values():
        # White text must stay readable on the primary colour (WCAG AA for normal text: 4.5:1).
        r, g, b = (int(theme["primary"][i : i + 2], 16) / 255 for i in (1, 3, 5))
        channel = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
        luminance = 0.2126 * channel[0] + 0.7152 * channel[1] + 0.0722 * channel[2]
        assert (1.05 / (luminance + 0.05)) >= 4.5, theme["label"]
