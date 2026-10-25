#!/usr/bin/env node
/**
 * Local development launcher (developer machines only — never deployed).
 *
 * `npm run dev` serves a hospital picker on http://localhost:5173. Choosing a hospital starts
 * that deployment's Django backend and Vite frontend as child processes, waits until both are
 * healthy and redirects the browser. Ctrl+C stops everything this launcher started.
 *
 * Each hospital is a separate deployment with its own database (ADR-003); this only automates
 * the commands documented in README.md. Security: binds to 127.0.0.1 only, accepts requests
 * only for its own host/origin (blocks DNS rebinding and cross-site requests), and can only run
 * the fixed commands defined in DEPLOYMENTS below.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LAUNCHER_PORT = Number(process.env.HIMS_LAUNCHER_PORT ?? 5173);
const FRONTEND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND_DIR = path.resolve(FRONTEND_DIR, "..", "backend");
const IS_WINDOWS = process.platform === "win32";
const PYTHON = path.join(
  BACKEND_DIR,
  ".venv",
  IS_WINDOWS ? "Scripts" : "bin",
  IS_WINDOWS ? "python.exe" : "python",
);
const VITE_BIN = path.join(FRONTEND_DIR, "node_modules", "vite", "bin", "vite.js");
const ALLOWED_HOSTS = new Set([`localhost:${LAUNCHER_PORT}`, `127.0.0.1:${LAUNCHER_PORT}`]);

const DEPLOYMENTS = {
  in: {
    name: "Indian Hospitals",
    flag: "🇮🇳",
    detail: "India deployment · INR · Asia/Kolkata",
    envFile: ".env",
    backendPort: 8000,
    frontendPort: 5175,
    viteMode: "in",
  },
  us: {
    name: "US Hospitals",
    flag: "🇺🇸",
    detail: "US deployment · USD · America/New_York",
    envFile: ".env.us",
    backendPort: 8001,
    frontendPort: 5174,
    viteMode: "us",
  },
  eu: {
    name: "European Hospitals",
    flag: "🇪🇺",
    detail: "Planned — not yet available",
    disabled: true,
  },
};

/** Running state per deployment: { backend, frontend } child processes and recent log lines. */
const state = Object.fromEntries(
  Object.keys(DEPLOYMENTS).map((key) => [key, { backend: null, frontend: null, logs: [] }]),
);

function log(key, source, text) {
  const lines = text.toString().split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    const entry = `[${source}] ${line}`;
    state[key].logs.push(entry);
    console.log(`${DEPLOYMENTS[key].flag} ${entry}`);
  }
  state[key].logs.splice(0, Math.max(0, state[key].logs.length - 200));
}

async function isHealthy(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
    return response.status < 500;
  } catch {
    return false;
  }
}

const backendHealthUrl = (d) => `http://127.0.0.1:${d.backendPort}/health/live/`;
const frontendUrl = (d) => `http://localhost:${d.frontendPort}/`;

function startProcess(key, source, command, args, options) {
  const child = spawn(command, args, { ...options, windowsHide: true });
  child.stdout.on("data", (data) => log(key, source, data));
  child.stderr.on("data", (data) => log(key, source, data));
  child.on("exit", (code) => {
    log(key, source, `process exited (code ${code})`);
    if (state[key][source] === child) state[key][source] = null;
  });
  child.on("error", (error) => log(key, source, `failed to start: ${error.message}`));
  return child;
}

async function startDeployment(key) {
  const d = DEPLOYMENTS[key];
  if (!d || d.disabled) throw new Error("This deployment is not available yet.");
  if (!existsSync(PYTHON)) {
    throw new Error(`Python virtual environment not found at ${PYTHON}. See README "Local development".`);
  }
  if (!existsSync(path.join(BACKEND_DIR, d.envFile))) {
    throw new Error(`backend/${d.envFile} is missing. See README "Running a second hospital locally".`);
  }

  // Reuse servers that are already up (e.g. started from another terminal).
  if (!state[key].backend && !(await isHealthy(backendHealthUrl(d)))) {
    const env = { ...process.env, PYTHONUNBUFFERED: "1", HIMS_ENV_FILE: d.envFile };
    state[key].backend = startProcess(
      key,
      "backend",
      PYTHON,
      ["manage.py", "runserver", `127.0.0.1:${d.backendPort}`],
      { cwd: BACKEND_DIR, env },
    );
  }
  if (!state[key].frontend && !(await isHealthy(frontendUrl(d)))) {
    state[key].frontend = startProcess(
      key,
      "frontend",
      process.execPath,
      [VITE_BIN, "--mode", d.viteMode],
      { cwd: FRONTEND_DIR, env: process.env },
    );
  }
}

function killTree(child) {
  if (!child || child.exitCode !== null) return;
  if (IS_WINDOWS) {
    // Django's autoreloader runs a child process; /T stops the whole tree.
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
}

function stopDeployment(key) {
  killTree(state[key].backend);
  killTree(state[key].frontend);
  state[key].backend = null;
  state[key].frontend = null;
  log(key, "launcher", "stopped");
}

async function status() {
  const result = {};
  for (const [key, d] of Object.entries(DEPLOYMENTS)) {
    if (d.disabled) {
      result[key] = { disabled: true };
      continue;
    }
    result[key] = {
      backendHealthy: await isHealthy(backendHealthUrl(d)),
      frontendHealthy: await isHealthy(frontendUrl(d)),
      managed: Boolean(state[key].backend || state[key].frontend),
      url: frontendUrl(d),
      logs: state[key].logs.slice(-40),
    };
  }
  return result;
}

function sendJson(res, code, body) {
  res.writeHead(code, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  // Only serve requests addressed to this launcher (defeats DNS rebinding).
  if (!ALLOWED_HOSTS.has(req.headers.host ?? "")) {
    res.writeHead(403).end("Forbidden");
    return;
  }
  const url = new URL(req.url ?? "/", `http://${req.headers.host}`);

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy":
        "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
      "X-Frame-Options": "DENY",
    });
    res.end(PAGE);
    return;
  }
  if (req.method === "GET" && url.pathname === "/api/status") {
    sendJson(res, 200, await status());
    return;
  }

  const match = url.pathname.match(/^\/api\/(start|stop)\/([a-z]+)$/);
  if (req.method === "POST" && match) {
    // Same-origin POSTs only: other websites cannot make the launcher start processes.
    const origin = req.headers.origin ?? "";
    if (!ALLOWED_HOSTS.has(origin.replace(/^https?:\/\//, "")) || !req.headers["x-launcher"]) {
      sendJson(res, 403, { error: "Forbidden" });
      return;
    }
    const [, action, key] = match;
    if (!(key in DEPLOYMENTS)) {
      sendJson(res, 404, { error: "Unknown deployment" });
      return;
    }
    try {
      if (action === "start") await startDeployment(key);
      else stopDeployment(key);
      sendJson(res, 200, { ok: true });
    } catch (error) {
      sendJson(res, 400, { error: error.message });
    }
    return;
  }
  res.writeHead(404).end("Not found");
});

function shutdown() {
  console.log("\nStopping all hospital servers started by the launcher...");
  for (const key of Object.keys(DEPLOYMENTS)) {
    if (!DEPLOYMENTS[key].disabled) stopDeployment(key);
  }
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

server.on("error", (error) => {
  if (error.code === "EADDRINUSE") {
    console.error(
      `Port ${LAUNCHER_PORT} is already in use. Close the other terminal running "npm run dev" and try again.`,
    );
    process.exit(1);
  }
  throw error;
});

/** True if something already accepts connections on host:port (IPv4 or IPv6 localhost). */
function portInUse(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    socket.setTimeout(500);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => resolve(false));
  });
}

// "localhost" may resolve to IPv6 first; an old Vite on [::1] would shadow the launcher.
if ((await portInUse("127.0.0.1", LAUNCHER_PORT)) || (await portInUse("::1", LAUNCHER_PORT))) {
  console.error(
    `Port ${LAUNCHER_PORT} is already in use (probably an old "npm run dev" terminal). ` +
      "Close it with Ctrl+C and run this again.",
  );
  process.exit(1);
}

server.listen(LAUNCHER_PORT, "127.0.0.1", () => {
  const url = `http://localhost:${LAUNCHER_PORT}/`;
  console.log(`HIMS local launcher: ${url}  (Ctrl+C stops everything)`);
  if (!process.argv.includes("--no-open")) {
    const opener = IS_WINDOWS ? ["cmd", ["/c", "start", "", url]] : [process.platform === "darwin" ? "open" : "xdg-open", [url]];
    spawn(opener[0], opener[1], { stdio: "ignore", detached: true, windowsHide: true }).unref();
  }
});

const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HIMS Launcher</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --text:#1b1f24; --muted:#5b6470; --border:#dde1e6;
          --accent:#1565c0; --ok:#2e7d32; --warn:#b26a00; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#111418; --card:#1a1f25; --text:#e8eaed; --muted:#9aa4b1; --border:#2c333b;
            --accent:#64b5f6; --ok:#81c784; --warn:#ffb74d; }
  }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
  main { max-width: 960px; margin: 0 auto; padding: 48px 16px; }
  h1 { margin:0 0 4px; font-size: 28px; }
  p.lead { margin:0 0 32px; color:var(--muted); }
  .grid { display:grid; gap:16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
  .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; display:flex; flex-direction:column; gap:12px; }
  .card.disabled { opacity:.55; }
  .title { display:flex; align-items:center; gap:12px; font-size:20px; font-weight:600; }
  .flag { font-size:32px; line-height:1; }
  .detail { color:var(--muted); font-size:14px; }
  .status { font-size:13px; color:var(--muted); min-height: 1.4em; }
  .status .ok { color:var(--ok); } .status .warn { color:var(--warn); }
  .actions { display:flex; gap:8px; margin-top:auto; }
  button { font: inherit; border-radius:8px; padding:10px 14px; cursor:pointer; border:1px solid var(--border); background:transparent; color:var(--text); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; flex:1; font-weight:600; }
  button:disabled { cursor:not-allowed; opacity:.6; }
  details { font-size:12px; }
  pre { max-height:220px; overflow:auto; background:var(--bg); padding:8px; border-radius:6px; white-space:pre-wrap; word-break:break-word; margin:8px 0 0; }
  footer { margin-top:32px; color:var(--muted); font-size:13px; }
</style>
</head>
<body>
<main>
  <h1>HIMS — choose a hospital deployment</h1>
  <p class="lead">Each region runs as its own deployment with its own database. Local development only.</p>
  <div class="grid" id="grid"></div>
  <footer>Servers keep running until you stop them here or press Ctrl+C in the launcher terminal.</footer>
</main>
<script>
const META = ${JSON.stringify(
  Object.fromEntries(
    Object.entries(DEPLOYMENTS).map(([k, d]) => [k, { name: d.name, flag: d.flag, detail: d.detail, disabled: !!d.disabled }]),
  ),
)};
const grid = document.getElementById("grid");
const busy = new Set();

function card(key, m) {
  const el = document.createElement("section");
  el.className = "card" + (m.disabled ? " disabled" : "");
  el.innerHTML =
    '<div class="title"><span class="flag"></span><span class="name"></span></div>' +
    '<div class="detail"></div><div class="status"></div>' +
    '<div class="actions"><button class="primary open"></button><button class="stop">Stop</button></div>' +
    '<details hidden><summary>Server output</summary><pre></pre></details>';
  el.querySelector(".flag").textContent = m.flag;
  el.querySelector(".name").textContent = m.name;
  el.querySelector(".detail").textContent = m.detail;
  const open = el.querySelector(".open");
  const stop = el.querySelector(".stop");
  if (m.disabled) {
    open.textContent = "Coming later"; open.disabled = true; stop.hidden = true;
  } else {
    open.textContent = "Open " + m.name;
    open.addEventListener("click", () => launch(key));
    stop.addEventListener("click", () => post("stop", key).then(refresh));
  }
  grid.appendChild(el);
  return el;
}

const cards = Object.fromEntries(Object.entries(META).map(([k, m]) => [k, card(k, m)]));

async function post(action, key) {
  const r = await fetch("/api/" + action + "/" + key, { method: "POST", headers: { "X-Launcher": "1" } });
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || "Request failed");
  return body;
}

function render(key, s) {
  const el = cards[key];
  if (s.disabled) return;
  const status = el.querySelector(".status");
  const parts = [
    s.backendHealthy ? '<span class="ok">● API running</span>' : '<span>○ API stopped</span>',
    s.frontendHealthy ? '<span class="ok">● App running</span>' : '<span>○ App stopped</span>',
  ];
  if (busy.has(key)) parts.push('<span class="warn">starting…</span>');
  status.innerHTML = parts.join(" &nbsp; ");
  el.querySelector(".stop").disabled = !s.managed;
  const details = el.querySelector("details");
  details.hidden = s.logs.length === 0;
  el.querySelector("pre").textContent = s.logs.join("\\n");
}

async function refresh() {
  const all = await (await fetch("/api/status")).json();
  for (const [key, s] of Object.entries(all)) render(key, s);
  return all;
}

async function launch(key) {
  const el = cards[key];
  const open = el.querySelector(".open");
  open.disabled = true;
  busy.add(key);
  try {
    await post("start", key);
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline) {
      const s = (await refresh())[key];
      if (s.backendHealthy && s.frontendHealthy) { window.location.href = s.url; return; }
      await new Promise((r) => setTimeout(r, 1000));
    }
    alert("The servers did not become ready in time. Open 'Server output' on the card for details.");
  } catch (e) {
    alert(e.message);
  } finally {
    busy.delete(key);
    open.disabled = false;
    refresh();
  }
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>`;
