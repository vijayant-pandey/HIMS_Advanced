import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { THEMES, readThemeId, saveThemeId, type ThemeId } from "./themes";

interface ThemeSelectionValue {
  themeId: ThemeId;
  setThemeId: (id: ThemeId) => void;
}

const ThemeSelectionContext = createContext<ThemeSelectionValue | null>(null);

const FONT_STACK = [
  "Inter",
  "-apple-system",
  "BlinkMacSystemFont",
  '"Segoe UI"',
  "Roboto",
  '"Helvetica Neue"',
  "Arial",
  "sans-serif",
].join(",");

const BORDER = "#e5e7eb";

/** Status chip/button colours used on every theme (see themes.test.ts). */
export const STATUS_COLORS = {
  info: "#01579b",
  warning: "#b45309",
  success: "#2e7d32",
  error: "#c62828",
} as const;

/**
 * Compact, modern look (HIMS-UI-002): 13px base text, a tighter type scale, flat bordered
 * surfaces, small sentence-case buttons and dense inputs/tables. Information-dense clinical
 * screens need more on screen without feeling crowded.
 */
function buildTheme(id: ThemeId) {
  const colors = THEMES[id];
  return createTheme({
    palette: {
      mode: "light",
      primary: { main: colors.primary, dark: colors.dark, contrastText: "#ffffff" },
      // Status colours dark enough for white text (WCAG AA 4.5:1; MUI's default blue "info" and
      // orange "warning" are 3.9 and 3.1). Checked in themes.test.ts.
      info: { main: STATUS_COLORS.info },
      warning: { main: STATUS_COLORS.warning },
      success: { main: STATUS_COLORS.success },
      error: { main: STATUS_COLORS.error },
      background: { default: "#f7f8fa", paper: "#ffffff" },
      divider: BORDER,
      text: { primary: "#1f2937", secondary: "#6b7280" },
      action: { selected: colors.tint, hover: "rgba(17, 24, 39, 0.04)" },
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily: FONT_STACK,
      fontSize: 13,
      h4: { fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.01em" },
      h5: { fontSize: "1.25rem", fontWeight: 600, letterSpacing: "-0.01em" },
      h6: { fontSize: "1rem", fontWeight: 600 },
      subtitle1: { fontSize: "0.95rem", fontWeight: 500 },
      body1: { fontSize: "0.875rem" },
      body2: { fontSize: "0.8125rem" },
      button: { textTransform: "none", fontWeight: 500, letterSpacing: 0 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: { body: { WebkitFontSmoothing: "antialiased" } },
      },
      MuiAppBar: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { border: 0, borderBottom: `1px solid ${colors.dark}` } },
      },
      MuiToolbar: { defaultProps: { variant: "dense" } },
      // Screen readers announce every loading bar as "Loading" (WCAG 4.1.2; HIMS-QA-001). A bar
      // can still pass its own aria-label.
      MuiLinearProgress: { defaultProps: { "aria-label": "Loading" } },
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { border: `1px solid ${BORDER}` } },
      },
      MuiButton: {
        defaultProps: { size: "small", disableElevation: true },
        styleOverrides: {
          root: { borderRadius: 6, paddingInline: 12, minHeight: 30 },
          sizeLarge: { minHeight: 36, fontSize: "0.875rem" },
        },
      },
      MuiIconButton: { defaultProps: { size: "small" } },
      MuiTextField: { defaultProps: { size: "small" } },
      MuiFormControl: { defaultProps: { size: "small" } },
      MuiInputBase: { styleOverrides: { root: { fontSize: "0.875rem" } } },
      MuiInputLabel: { styleOverrides: { root: { fontSize: "0.875rem" } } },
      MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 6 } } },
      MuiMenu: { defaultProps: { slotProps: { paper: { elevation: 4 } } } },
      MuiMenuItem: { styleOverrides: { root: { fontSize: "0.8125rem", minHeight: 32 } } },
      MuiTable: { defaultProps: { size: "small" } },
      MuiTableHead: {
        styleOverrides: { root: { backgroundColor: colors.tint } },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { borderColor: BORDER, paddingTop: 8, paddingBottom: 8 },
          head: { fontWeight: 600, color: "#374151", fontSize: "0.75rem" },
        },
      },
      MuiChip: { defaultProps: { size: "small" } },
      MuiAlert: { styleOverrides: { root: { fontSize: "0.8125rem", borderRadius: 8 } } },
      MuiDialog: { defaultProps: { slotProps: { paper: { elevation: 8 } } } },
      MuiDialogTitle: { styleOverrides: { root: { fontSize: "1rem", fontWeight: 600 } } },
    },
  });
}

export function ThemeSelectionProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeIdState] = useState<ThemeId>(readThemeId);

  // A theme picked in another tab (e.g. the launcher) applies when you come back to this one.
  useEffect(() => {
    const sync = () => setThemeIdState(readThemeId());
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);
    return () => {
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);

  const value = useMemo<ThemeSelectionValue>(
    () => ({
      themeId,
      setThemeId: (id) => {
        saveThemeId(id);
        setThemeIdState(id);
      },
    }),
    [themeId],
  );
  const theme = useMemo(() => buildTheme(themeId), [themeId]);

  return (
    <ThemeSelectionContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeSelectionContext.Provider>
  );
}

export function useThemeSelection(): ThemeSelectionValue {
  const value = useContext(ThemeSelectionContext);
  if (!value) throw new Error("useThemeSelection must be used inside ThemeSelectionProvider");
  return value;
}
