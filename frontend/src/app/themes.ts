/**
 * UI colour themes. The choice is a non-sensitive preference kept in the `hims_theme` cookie so
 * the launcher, both hospital apps and the Django admin (all on localhost) share it.
 * Keep THEMES in sync with backend/common/theming.py.
 */

export const THEME_IDS = ["blue", "red", "green", "mono"] as const;
export type ThemeId = (typeof THEME_IDS)[number];

export interface ThemeColors {
  label: string;
  primary: string;
  dark: string;
  tint: string;
}

export const THEMES: Record<ThemeId, ThemeColors> = {
  blue: { label: "White & Blue", primary: "#1565c0", dark: "#0d47a1", tint: "#e3f2fd" },
  red: { label: "White & Red", primary: "#c62828", dark: "#8e0000", tint: "#ffebee" },
  green: { label: "White & Green", primary: "#2e7d32", dark: "#1b5e20", tint: "#e8f5e9" },
  mono: { label: "Minimal Black & White", primary: "#111111", dark: "#000000", tint: "#f2f2f2" },
};

export const DEFAULT_THEME: ThemeId = "blue";
const COOKIE = "hims_theme";

function isThemeId(value: string | null | undefined): value is ThemeId {
  return !!value && (THEME_IDS as readonly string[]).includes(value);
}

export function readThemeId(): ThemeId {
  const match = document.cookie.match(/(?:^|;\s*)hims_theme=([^;]+)/);
  const value = match?.[1] ? decodeURIComponent(match[1]) : null;
  return isThemeId(value) ? value : DEFAULT_THEME;
}

export function saveThemeId(id: ThemeId): void {
  document.cookie = `${COOKIE}=${id}; path=/; max-age=31536000; SameSite=Lax`;
}
