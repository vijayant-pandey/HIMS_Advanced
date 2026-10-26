import { Alert, Box, Button, Stack, Typography } from "@mui/material";
import { useState } from "react";

/** Shows backup codes once, with copy and download, so the person can store them safely. */
export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  const download = () => {
    const blob = new Blob(
      [`HIMS backup codes (each works once)\n\n${text}\n`],
      { type: "text/plain" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "hims-backup-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Stack spacing={2}>
      <Alert severity="warning">
        Save these backup codes now. They are shown only once. Each code works one time if you
        lose your phone.
      </Alert>
      <Box
        component="ol"
        sx={{
          m: 0,
          p: 2,
          pl: 4,
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          gap: 0.5,
          fontFamily: "monospace",
          fontSize: "0.95rem",
          bgcolor: "background.default",
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
        }}
        data-testid="recovery-codes"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </Box>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button
          variant="outlined"
          onClick={() =>
            navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined)
          }
        >
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button variant="outlined" onClick={download}>
          Download .txt
        </Button>
        <Button variant="contained" onClick={onDone}>
          I've saved them
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Keep them somewhere safe and private, for example a password manager or a printed copy
        in a locked drawer.
      </Typography>
    </Stack>
  );
}
