import { AppBar, Box, Button, Container, Stack, Toolbar, Typography } from "@mui/material";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { ThemePicker } from "../components/ThemePicker";
import { useCurrentUser, useLogout } from "../features/auth/api";
import { visibleNavItems } from "./navigation";

export function AppShell() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

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
                sx={{ opacity: 0.85, "&.active": { opacity: 1, bgcolor: "rgba(255,255,255,0.16)" } }}
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
            sx={{ opacity: 0.9, "&.active": { opacity: 1, bgcolor: "rgba(255,255,255,0.16)" } }}
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
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Outlet />
      </Container>
    </Box>
  );
}
