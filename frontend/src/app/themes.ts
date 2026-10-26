/**
 * UI colour themes. The choice is a non-sensitive preference kept in the `hims_theme` cookie so
 * the launcher, both hospital apps and the Django admin (all on localhost) share it.
 *
 * Colours live in themes.json, which the launcher also reads. The Django admin keeps a copy in
 * backend/common/theming.py; a backend test fails if the two ever differ.
 */
import palette from "./themes.json";

export interface ThemeColors {
  label: string;
  primary: string;
  dark: string;
  tint: string;
}

export type ThemeId = keyof typeof palette;

export const THEMES: Record<ThemeId, ThemeColors> = palette;
export const THEME_IDS = Object.keys(palette) as ThemeId[];
export const DEFAULT_THEME: ThemeId = "blue";
const COOKIE = "hims_theme";

function isThemeId(value: string | null | undefined): value is ThemeId {
  return !!value && Object.hasOwn(palette, value);
}

export function readThemeId(): ThemeId {
  const match = document.cookie.match(/(?:^|;\s*)hims_theme=([^;]+)/);
  const value = match?.[1] ? decodeURIComponent(match[1]) : null;
  return isThemeId(value) ? value : DEFAULT_THEME;
}

export function saveThemeId(id: ThemeId): void {
  document.cookie = `${COOKIE}=${id}; path=/; max-age=31536000; SameSite=Lax`;
}
