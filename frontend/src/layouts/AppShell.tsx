import { AppBar, Box, Button, Container, Stack, Toolbar, Typography } from "@mui/material";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useCurrentUser, useLogout } from "../features/auth/api";
import { hasPermission } from "../features/auth/grants";

const NAV_ITEMS = [
  { to: "/facilities", label: "Facilities", permission: "facilities.view" },
  { to: "/staff", label: "Staff", permission: "staff.view" },
];

export function AppShell() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar sx={{ gap: 2, flexWrap: "wrap" }}>
          <Typography variant="h6" component="div" sx={{ mr: 2 }}>
            HIMS
          </Typography>
          <Stack direction="row" spacing={1} component="nav" sx={{ flexGrow: 1 }}>
            {NAV_ITEMS.filter((item) => hasPermission(user, item.permission)).map((item) => (
              <Button key={item.to} color="inherit" component={NavLink} to={item.to}>
                {item.label}
              </Button>
            ))}
          </Stack>
          <Typography variant="body2">{user?.display_name}</Typography>
          <Button
            color="inherit"
            variant="outlined"
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
