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
