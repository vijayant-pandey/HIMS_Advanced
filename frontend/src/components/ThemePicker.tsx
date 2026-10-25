import { Box, Button, ListItemIcon, Menu, MenuItem } from "@mui/material";
import { useState } from "react";

import { useThemeSelection } from "../app/ThemeSelection";
import { THEMES, THEME_IDS } from "../app/themes";

function Swatch({ color }: { color: string }) {
  return (
    <Box
      component="span"
      sx={{
        width: 16,
        height: 16,
        borderRadius: "50%",
        bgcolor: color,
        border: "2px solid #ffffff",
        boxShadow: "0 0 0 1px rgba(0,0,0,0.25)",
        display: "inline-block",
      }}
    />
  );
}

/** Theme menu. `color="inherit"` suits an app bar; the default suits a light page. */
export function ThemePicker({ color = "primary" }: { color?: "inherit" | "primary" }) {
  const { themeId, setThemeId } = useThemeSelection();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  return (
    <>
      <Button
        color={color}
        variant="outlined"
        size="small"
        startIcon={<Swatch color={THEMES[themeId].primary} />}
        onClick={(event) => setAnchor(event.currentTarget)}
        aria-haspopup="menu"
      >
        Theme
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {THEME_IDS.map((id) => (
          <MenuItem
            key={id}
            selected={id === themeId}
            onClick={() => {
              setThemeId(id);
              setAnchor(null);
            }}
          >
            <ListItemIcon>
              <Swatch color={THEMES[id].primary} />
            </ListItemIcon>
            {THEMES[id].label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
