import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { THEMES, readThemeId, saveThemeId, type ThemeId } from "./themes";

interface ThemeSelectionValue {
  themeId: ThemeId;
  setThemeId: (id: ThemeId) => void;
}

const ThemeSelectionContext = createContext<ThemeSelectionValue | null>(null);

function buildTheme(id: ThemeId) {
  const colors = THEMES[id];
  return createTheme({
    palette: {
      mode: "light",
      primary: { main: colors.primary, dark: colors.dark, contrastText: "#ffffff" },
      background: { default: "#f8f9fb", paper: "#ffffff" },
      action: { selected: colors.tint },
    },
    shape: { borderRadius: 8 },
    components: {
      MuiAppBar: { defaultProps: { elevation: 0 } },
      MuiTableHead: {
        styleOverrides: { root: { backgroundColor: colors.tint } },
      },
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
