"""UI colour themes shared by the React apps, the local launcher and the Django admin.

The selected theme is a non-sensitive preference stored in the ``hims_theme`` cookie. The
source of truth is ``frontend/src/app/themes.json``; this copy lets the Django admin render
without depending on frontend files at runtime. ``common/tests/test_theming.py`` fails if they
ever differ.
"""

THEME_COOKIE = "hims_theme"
DEFAULT_THEME = "blue"


def _theme(label: str, primary: str, dark: str, tint: str) -> dict:
    return {"label": label, "primary": primary, "dark": dark, "tint": tint}


# primary: main colour; dark: headers/buttons hover; tint: light background accents.
THEMES = {
    "blue": _theme("White & Blue", "#1565c0", "#0d47a1", "#e3f2fd"),
    "red": _theme("White & Red", "#c62828", "#8e0000", "#ffebee"),
    "green": _theme("White & Green", "#2e7d32", "#1b5e20", "#e8f5e9"),
    "mono": _theme("Minimal Black & White", "#111111", "#000000", "#f2f2f2"),
    "purple": _theme("White & Purple", "#7e22ce", "#6b21a8", "#faf5ff"),
    "teal": _theme("White & Teal", "#0f766e", "#115e59", "#f0fdfa"),
    "orange": _theme("White & Orange", "#c2410c", "#9a3412", "#fff7ed"),
    "indigo": _theme("White & Indigo", "#4338ca", "#3730a3", "#eef2ff"),
    "rose": _theme("White & Rose", "#be123c", "#9f1239", "#fff1f2"),
    "slate": _theme("White & Slate", "#334155", "#1e293b", "#f1f5f9"),
}


def theme_context(request):
    """Template context processor: the validated current theme (never raw cookie text)."""
    theme_id = request.COOKIES.get(THEME_COOKIE, DEFAULT_THEME)
    if theme_id not in THEMES:
        theme_id = DEFAULT_THEME
    return {"hims_theme": {"id": theme_id, **THEMES[theme_id]}}
