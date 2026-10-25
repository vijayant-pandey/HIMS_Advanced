import { DEFAULT_THEME, readThemeId, saveThemeId } from "./themes";

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
    document.cookie = "hims_theme=purple; path=/";
    expect(readThemeId()).toBe(DEFAULT_THEME);
  });
});
