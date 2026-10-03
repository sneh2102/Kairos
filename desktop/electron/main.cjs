// Electron main process: spawns the Python/FastAPI backend, waits for it to
// be healthy, then opens the window. Kills the backend on quit.
const { app, BrowserWindow, ipcMain, shell, dialog, Tray, Menu, nativeImage } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");
const crypto = require("crypto");

const BACKEND_PORT = 8756;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const BACKEND_ROOT = path.join(__dirname, "..", "..");
const isDev = !app.isPackaged;
// Bundled binaries are named server.exe/tectonic.exe/cloudflared.exe on Windows,
// and server/tectonic/cloudflared (no extension) on macOS/Linux.
const EXE = process.platform === "win32" ? ".exe" : "";

// package.json's "name" is "desktop" (npm workspace convention) — without
// this, Electron uses that for app.getPath('userData'), landing user data in
// a confusingly generic %APPDATA%\desktop instead of \Job Scraper.
app.setName("Job Scraper");

let backendProcess = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;

// config.json lives wherever the backend looks for it (config.py's DATA_DIR):
// the OS per-user data dir when packaged, the repo root in dev. Read fresh on
// every close rather than cached, so a change made in Settings takes effect
// without restarting the app.
const CONFIG_PATH = app.isPackaged
  ? path.join(app.getPath("userData"), "config.json")
  : path.join(BACKEND_ROOT, "config.json");

function getDesktopConfig() {
  try {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    return { runInBackground: false, launchOnStartup: false, ...raw.desktop };
  } catch {
    return { runInBackground: false, launchOnStartup: false };
  }
}

// Per-install shared secret for mobile tunnel traffic. Generated once on first
// run, persisted in userData, reused after. The backend checks it
// (TUNNEL_TOKEN); mobile/config.ts sends it (API_TOKEN) — both must match, so
// we pass it to the backend on launch and write it into config.ts when the
// mobile bridge starts. No secret is committed to the repo.
function mobileToken() {
  const f = path.join(app.getPath("userData"), "mobile-token");
  try {
    const existing = fs.readFileSync(f, "utf-8").trim();
    if (existing) return existing;
  } catch { /* first run */ }
  const t = crypto.randomBytes(32).toString("base64url");
  fs.writeFileSync(f, t);
  return t;
}
let MOBILE_TOKEN = null; // set in startBackend (needs app to be ready)

function pythonExe() {
  const venvPython = process.platform === "win32"
    ? path.join(BACKEND_ROOT, "venv", "Scripts", "python.exe")
    : path.join(BACKEND_ROOT, "venv", "bin", "python");
  return fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "python" : "python3");
}

function startBackend() {
  MOBILE_TOKEN = mobileToken();
  const userData = app.getPath("userData");
  const logPath = path.join(userData, "app.log");
  const logStream = fs.createWriteStream(logPath, { flags: "a" });

  function logToFile(prefix, data) {
    const timestamp = new Date().toISOString();
    const message = `[${timestamp}] [${prefix}] ${data}`;
    process.stdout.write(message);
    logStream.write(message);
  }

  if (app.isPackaged) {
    // Frozen (PyInstaller) backend + bundled Chromium/Tectonic, laid out by
    // electron-builder's extraResources under resourcesPath. User data
    // (config/resume/db) lives in the OS per-user data dir, never inside the
    // read-only installed app folder.

    // Try multiple possible paths for the backend executable (handles different bundle layouts)
    const backendPaths = [
      path.join(process.resourcesPath, "backend", "server", "server" + EXE),
      path.join(process.resourcesPath, "backend", "server" + EXE),
    ];

    let backendExe = null;
    for (const candidate of backendPaths) {
      if (fs.existsSync(candidate)) {
        backendExe = candidate;
        break;
      }
    }

    if (!backendExe) {
      const errorMsg = `Backend executable not found. Searched:\n${backendPaths.join("\n")}\n\nresourcesPath: ${process.resourcesPath}`;
      logToFile("error", `${errorMsg}\n`);
      throw new Error(errorMsg);
    }

    logToFile("startup", `Starting backend from: ${backendExe}\n`);

    backendProcess = spawn(backendExe, [], {
      cwd: userData,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        JOB_HUNTER_DATA_DIR: userData,
        // Let Playwright use its default cache location (~/.cache/ms-playwright)
        // instead of trying to use non-existent bundled browsers
        TECTONIC_PATH: path.join(process.resourcesPath, "tectonic", "tectonic" + EXE),
        RESUME_ICON_DIR: path.join(process.resourcesPath, "resume-icons"),
        TUNNEL_TOKEN: MOBILE_TOKEN,
      },
    });
  } else {
    backendProcess = spawn(pythonExe(), ["-m", "uvicorn", "server:app", "--port", String(BACKEND_PORT)], {
      cwd: BACKEND_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, TUNNEL_TOKEN: MOBILE_TOKEN },
    });
  }

  backendProcess.stdout.on("data", (d) => logToFile("backend", d.toString()));
  backendProcess.stderr.on("data", (d) => logToFile("backend:err", d.toString()));
  backendProcess.on("error", (err) => {
    logToFile("error", `Backend spawn error: ${err.message}\n`);
    if (mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        "Backend Error",
        `Failed to start backend process:\n\n${err.message}`
      );
    }
  });
  backendProcess.on("exit", (code) => {
    logToFile("backend", `Backend exited with code ${code}\n`);
    backendProcess = null;

    if (!isQuitting && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        "Application Error",
        "The backend process crashed. Please restart the application.\n\n" +
        `Check the log file at: ${logPath}`
      );
      mainWindow.close();
    }
  });
}

function waitForHealth(timeoutMs = 30000) {
  const start = Date.now();
  let lastError = null;
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(`${BACKEND_URL}/api/health`, (res) => {
          if (res.statusCode === 200) return resolve();
          retry();
        })
        .on("error", (err) => {
          lastError = err;
          retry();
        });
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) {
        const msg = lastError
          ? `Backend health check timed out (${lastError.code}). Backend may have crashed or failed to start.`
          : `Backend health check timed out after ${timeoutMs}ms. Backend is not responding on port ${BACKEND_PORT}.`;
        return reject(new Error(msg));
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    backgroundColor: "#0d1117",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  // "Run in background" setting: hide to tray instead of quitting, so the
  // backend keeps scraping/applying after the window closes. Off by default —
  // closing quits like a normal app unless the user opted in.
  mainWindow.on("close", (e) => {
    if (isQuitting || !getDesktopConfig().runInBackground) return;
    e.preventDefault();
    mainWindow.hide();
  });

  try {
    await waitForHealth();
  } catch (e) {
    console.error("Backend health check failed:", e);
    const logPath = path.join(app.getPath("userData"), "app.log");
    dialog.showErrorBox(
      "Backend Failed to Start",
      `The application backend could not start. This usually means:\n\n` +
      `• Missing or incorrect API keys in Settings\n` +
      `• Required Python dependencies are not properly installed\n` +
      `• Another process is using port ${BACKEND_PORT}\n` +
      `• Corrupted database or configuration file\n\n` +
      `Please check the log file at:\n${logPath}\n\n` +
      `Error: ${e.message}`
    );
    mainWindow.close();
    return;
  }

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

// ---------------------------------------------------------------------------
// Mobile bridge: one button stands up everything a phone needs. Two Cloudflare
// tunnels (Expo's own --tunnel/ngrok is flaky and needs an account) — one to
// the backend so the phone can reach the API, one to Metro so Expo Go can load
// the app's JS over any network. We point Expo at the Metro tunnel via
// EXPO_PACKAGER_PROXY_URL so it serves absolute https bundle URLs through it;
// the QR is that same tunnel URL with an exp:// scheme. All three children die
// on quit alongside the backend.
// ---------------------------------------------------------------------------
// Packaged: the Expo project ships as an extraResource under resources/mobile
// (real files on disk — node_modules can't live in the asar and Expo/Metro
// need to read them). Dev: it's the repo's mobile/ folder. The oneClick NSIS
// install is per-user (%LOCALAPPDATA%), so this dir is writable — Metro's
// .expo cache and our config.ts rewrite both work in place.
// ponytail: in-place run assumes a writable install dir (true for per-user
// NSIS); if this ever ships perMachine, copy resources/mobile → userData on
// first start and run from there.
const MOBILE_DIR = app.isPackaged
  ? path.join(process.resourcesPath, "mobile")
  : path.join(BACKEND_ROOT, "mobile");
const MOBILE_CONFIG = path.join(MOBILE_DIR, "config.ts");
const METRO_PORT = 8081;

let cfBackend = null; // tunnel → backend API
let cfMetro = null; // tunnel → Metro dev server
let expoProcess = null;
let mobileState = { phase: "idle", backendUrl: null, expoUrl: null, error: null };

function setMobile(patch) {
  mobileState = { ...mobileState, ...patch };
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("mobile:status", mobileState);
}

function cloudflaredPath() {
  const bundled = app.isPackaged
    ? path.join(process.resourcesPath, "cloudflared", "cloudflared" + EXE)
    : path.join(__dirname, "..", "build-resources", "cloudflared", "cloudflared" + EXE);
  return fs.existsSync(bundled) ? bundled : "cloudflared"; // fall back to PATH
}

function writeMobileConfig(url) {
  // Stamp the freshly-generated tunnel URL and this install's token into
  // config.ts so the phone app talks to the right backend with the matching
  // secret. Both change per install / per run; nothing is hardcoded.
  const src = fs.readFileSync(MOBILE_CONFIG, "utf-8");
  const next = src
    .replace(/export const API_BASE = "[^"]*";/, `export const API_BASE = "${url}";`)
    .replace(/export const API_TOKEN = "[^"]*";/, `export const API_TOKEN = "${MOBILE_TOKEN}";`);
  fs.writeFileSync(MOBILE_CONFIG, next);
}

// Spawn a quick trycloudflare tunnel to a local port; onUrl fires once with the
// public https URL (cloudflared logs it to stderr).
function startCloudflared(port, onUrl) {
  const proc = spawn(cloudflaredPath(), ["tunnel", "--url", `http://127.0.0.1:${port}`], { cwd: BACKEND_ROOT });
  let done = false;
  const onData = (d) => {
    const s = d.toString();
    process.stdout.write(`[cf:${port}] ${s}`);
    const m = s.match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);
    if (m && !done) { done = true; onUrl(m[0]); }
  };
  proc.stdout.on("data", onData);
  proc.stderr.on("data", onData);
  proc.on("error", (e) => setMobile({ phase: "error", error: `cloudflared: ${e.message}` }));
  return proc;
}

function startExpo(proxyUrl) {
  // ELECTRON_RUN_AS_NODE runs the Expo CLI on Electron's bundled Node, so no
  // system Node is required once packaged. EXPO_PACKAGER_PROXY_URL makes Metro
  // serve absolute URLs through the Cloudflare tunnel instead of the LAN IP.
  // ponytail: swap to a bundled node if Metro subprocess inheritance misbehaves.
  const cli = path.join(MOBILE_DIR, "node_modules", "expo", "bin", "cli");
  expoProcess = spawn(process.execPath, [cli, "start", "--port", String(METRO_PORT)], {
    cwd: MOBILE_DIR,
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1", EXPO_PACKAGER_PROXY_URL: proxyUrl },
  });
  expoProcess.stdout.on("data", (d) => process.stdout.write(`[expo] ${d}`));
  expoProcess.stderr.on("data", (d) => process.stdout.write(`[expo] ${d}`));
  expoProcess.on("error", (e) => setMobile({ phase: "error", error: `expo: ${e.message}` }));
  expoProcess.on("exit", () => { expoProcess = null; });
}

function stopMobile() {
  for (const p of [expoProcess, cfMetro, cfBackend]) if (p) p.kill();
  expoProcess = cfMetro = cfBackend = null;
  setMobile({ phase: "idle", backendUrl: null, expoUrl: null, error: null });
}

ipcMain.handle("mobile:start", () => {
  if (mobileState.phase !== "idle" && mobileState.phase !== "error") return mobileState;
  setMobile({ phase: "starting-tunnel", backendUrl: null, expoUrl: null, error: null });
  cfBackend = startCloudflared(BACKEND_PORT, (url) => {
    writeMobileConfig(url);
    setMobile({ phase: "starting-expo", backendUrl: url });
    cfMetro = startCloudflared(METRO_PORT, (metroUrl) => {
      startExpo(metroUrl); // proxy env must be set before Metro bundles
      setMobile({ phase: "ready", expoUrl: metroUrl.replace("https://", "exp://") });
    });
  });
  return mobileState;
});
ipcMain.handle("mobile:stop", () => { stopMobile(); return mobileState; });
ipcMain.handle("mobile:status", () => mobileState);

ipcMain.handle("backend:url", () => BACKEND_URL);

ipcMain.handle("desktop:get-launch-on-startup", () => app.getLoginItemSettings().openAtLogin);
ipcMain.handle("desktop:set-launch-on-startup", (_e, enabled) => {
  app.setLoginItemSettings({ openAtLogin: enabled, openAsHidden: true });
});

// System tray icon — lets a window hidden by "run in background" be reopened,
// and gives an explicit Quit that actually exits (vs. the X button, which
// hides instead of closing when that setting is on). Reuses the mobile app's
// icon.png so no separate icon asset needs to ship with the desktop build.
function createTray() {
  const iconPath = path.join(MOBILE_DIR, "assets", "icon.png");
  let image = nativeImage.createFromPath(iconPath);
  if (!image.isEmpty()) image = image.resize({ width: 16, height: 16 });
  tray = new Tray(image);
  tray.setToolTip("Kairos");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Kairos", click: () => { mainWindow?.show(); mainWindow?.focus(); } },
      { type: "separator" },
      { label: "Quit", click: () => { isQuitting = true; app.quit(); } },
    ])
  );
  tray.on("click", () => { mainWindow?.show(); mainWindow?.focus(); });
}

ipcMain.handle("dialog:pick-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(async () => {
  try {
    startBackend();
    await createWindow();
    createTray();
  } catch (err) {
    console.error("Failed to start application:", err);
    dialog.showErrorBox("Startup Error", `Failed to start application: ${err.message}`);
    app.quit();
    return;
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  stopMobile();
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
