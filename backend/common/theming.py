"""UI colour themes shared by the React apps, the local launcher and the Django admin.

The selected theme is a non-sensitive preference stored in the ``hims_theme`` cookie. Keep
THEMES in sync with ``frontend/src/app/themes.ts``.
"""

THEME_COOKIE = "hims_theme"
DEFAULT_THEME = "blue"

# primary: main colour; dark: headers/buttons hover; tint: light background accents.
THEMES = {
    "blue": {"label": "White & Blue", "primary": "#1565c0", "dark": "#0d47a1", "tint": "#e3f2fd"},
    "red": {"label": "White & Red", "primary": "#c62828", "dark": "#8e0000", "tint": "#ffebee"},
    "green": {"label": "White & Green", "primary": "#2e7d32", "dark": "#1b5e20", "tint": "#e8f5e9"},
    "mono": {
        "label": "Minimal Black & White",
        "primary": "#111111",
        "dark": "#000000",
        "tint": "#f2f2f2",
    },
}


def theme_context(request):
    """Template context processor: the validated current theme (never raw cookie text)."""
    theme_id = request.COOKIES.get(THEME_COOKIE, DEFAULT_THEME)
    if theme_id not in THEMES:
        theme_id = DEFAULT_THEME
    return {"hims_theme": {"id": theme_id, **THEMES[theme_id]}}
