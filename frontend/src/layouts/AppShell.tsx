import { AppBar, Box, Button, Container, LinearProgress, Stack, Toolbar, Typography } from "@mui/material";
import { NavLink, Outlet, useNavigate, useNavigation } from "react-router-dom";

import { ThemePicker } from "../components/ThemePicker";
import { useCurrentUser, useLogout } from "../features/auth/api";
import { MENU_ACTIVE_SHADE, MENU_TEXT_OPACITY, hasNestedItem, visibleNavItems } from "./navigation";

/**
 * Menu items: the current page is darkened and underlined (not lightened), so white text keeps
 * at least 4.5:1 contrast on every theme (WCAG 2.1 AA; checked in themes.test.ts and by the
 * browser accessibility tests, HIMS-QA-001).
 */
export const MENU_ITEM = {
  opacity: MENU_TEXT_OPACITY,
  "&.active": {
    opacity: 1,
    bgcolor: `rgba(0,0,0,${MENU_ACTIVE_SHADE})`,
    textDecoration: "underline",
    textUnderlineOffset: "4px",
  },
} as const;

export function AppShell() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const navigation = useNavigation();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="sticky">
        <Toolbar sx={{ gap: 1.5, flexWrap: "wrap" }}>
          <Typography
            variant="subtitle1"
            component={NavLink}
            to="/"
            sx={{ mr: 2, fontWeight: 700, color: "inherit", textDecoration: "none" }}
          >
            HIMS
          </Typography>
          <Stack direction="row" spacing={0.5} component="nav" sx={{ flexGrow: 1 }}>
            {visibleNavItems(user).map((item) => (
              <Button
                key={item.to}
                color="inherit"
                component={NavLink}
                to={item.to}
                end={hasNestedItem(item)}
                sx={MENU_ITEM}
              >
                {item.label}
              </Button>
            ))}
          </Stack>
          <ThemePicker color="inherit" />
          <Button
            color="inherit"
            component={NavLink}
            to="/security"
            title="Security: two-factor sign-in"
            sx={MENU_ITEM}
          >
            {user?.display_name} · Security
          </Button>
          <Button
            color="inherit"
            variant="outlined"
            sx={{ borderColor: "rgba(255,255,255,0.5)" }}
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
          >
            Sign out
          </Button>
        </Toolbar>
      </AppBar>
      {/* A screen opened for the first time is being downloaded (code splitting, HIMS-PLAT-015). */}
      <Box sx={{ height: 4 }}>{navigation.state === "loading" && <LinearProgress aria-label="Loading" />}</Box>
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Outlet />
      </Container>
    </Box>
  );
}
