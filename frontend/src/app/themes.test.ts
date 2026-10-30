import { MENU_ACTIVE_SHADE, MENU_TEXT_OPACITY } from "../layouts/navigation";
import { STATUS_COLORS } from "./ThemeSelection";
import { DEFAULT_THEME, THEME_IDS, THEMES, readThemeId, saveThemeId } from "./themes";

describe("theme preference", () => {
  afterEach(() => {
    document.cookie = "hims_theme=; path=/; max-age=0";
  });

  it("defaults to white and blue", () => {
    expect(readThemeId()).toBe(DEFAULT_THEME);
    expect(DEFAULT_THEME).toBe("blue");
  });

  it("persists the chosen theme in the shared cookie", () => {
    saveThemeId("green");
    expect(readThemeId()).toBe("green");
  });

  it("ignores unknown cookie values", () => {
    document.cookie = "hims_theme=chartreuse; path=/";
    expect(readThemeId()).toBe(DEFAULT_THEME);
  });
});

describe("theme catalog", () => {
  it("offers the four original themes plus six more", () => {
    expect(THEME_IDS).toHaveLength(10);
    expect(THEME_IDS.slice(0, 4)).toEqual(["blue", "red", "green", "mono"]);
    for (const id of THEME_IDS) expect(THEMES[id].primary).toMatch(/^#[0-9a-f]{6}$/);
  });
});

// WCAG 2.1 AA: normal text needs a contrast ratio of at least 4.5:1 (spec 18 accessibility).
type Rgb = [number, number, number];
const hex = (value: string): Rgb => [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16)) as Rgb;
const mix = (top: Rgb, bottom: Rgb, alpha: number): Rgb =>
  top.map((channel, i) => channel * alpha + bottom[i]! * (1 - alpha)) as Rgb;
function luminance([r, g, b]: Rgb): number {
  const linear = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}
function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

describe("menu bar contrast on every theme (HIMS-QA-001)", () => {
  const white: Rgb = [255, 255, 255];
  const black: Rgb = [0, 0, 0];
  it.each(THEME_IDS)("%s: menu text, current page and header are readable", (id) => {
    const bar = hex(THEMES[id].primary);
    const menuText = mix(white, bar, MENU_TEXT_OPACITY);
    const currentPage = mix(black, bar, MENU_ACTIVE_SHADE);
    expect(contrast(white, bar), "header text").toBeGreaterThanOrEqual(4.5);
    expect(contrast(menuText, bar), "menu item").toBeGreaterThanOrEqual(4.5);
    expect(contrast(white, currentPage), "current page").toBeGreaterThanOrEqual(4.5);
  });
});

describe("status colours (HIMS-QA-001)", () => {
  it.each(["info", "warning", "success", "error"] as const)("%s chips keep white text readable", (name) => {
    expect(contrast([255, 255, 255], hex(STATUS_COLORS[name]))).toBeGreaterThanOrEqual(4.5);
  });
});
