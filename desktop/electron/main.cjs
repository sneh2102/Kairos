// Electron main process: spawns the Python/FastAPI backend, waits for it to
// be healthy, then opens the window. Kills the backend on quit.
const { app, BrowserWindow, ipcMain, shell, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const BACKEND_PORT = 8756;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const BACKEND_ROOT = path.join(__dirname, "..", "..");
const isDev = !app.isPackaged;

// package.json's "name" is "desktop" (npm workspace convention) — without
// this, Electron uses that for app.getPath('userData'), landing user data in
// a confusingly generic %APPDATA%\desktop instead of \Job Scraper.
app.setName("Job Scraper");

let backendProcess = null;
let mainWindow = null;

function pythonExe() {
  const venvPython = process.platform === "win32"
    ? path.join(BACKEND_ROOT, "venv", "Scripts", "python.exe")
    : path.join(BACKEND_ROOT, "venv", "bin", "python");
  return fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "python" : "python3");
}

function startBackend() {
  if (app.isPackaged) {
    // Frozen (PyInstaller) backend + bundled Chromium/Tectonic, laid out by
    // electron-builder's extraResources under resourcesPath. User data
    // (config/resume/db) lives in the OS per-user data dir, never inside the
    // read-only installed app folder.
    const backendExe = path.join(process.resourcesPath, "backend", "server.exe");
    backendProcess = spawn(backendExe, [], {
      cwd: path.dirname(backendExe),
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        JOB_HUNTER_DATA_DIR: app.getPath("userData"),
        PLAYWRIGHT_BROWSERS_PATH: path.join(process.resourcesPath, "chromium"),
        TECTONIC_PATH: path.join(process.resourcesPath, "tectonic", "tectonic.exe"),
        RESUME_ICON_DIR: path.join(process.resourcesPath, "resume-icons"),
      },
    });
  } else {
    backendProcess = spawn(pythonExe(), ["-m", "uvicorn", "server:app", "--port", String(BACKEND_PORT)], {
      cwd: BACKEND_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
  }
  backendProcess.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backendProcess.stderr.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  backendProcess.on("exit", (code) => {
    console.log(`Backend exited with code ${code}`);
    backendProcess = null;
  });
}

function waitForHealth(timeoutMs = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(`${BACKEND_URL}/api/health`, (res) => {
          if (res.statusCode === 200) return resolve();
          retry();
        })
        .on("error", retry);
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) return reject(new Error("Backend health check timed out"));
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

  try {
    await waitForHealth();
  } catch (e) {
    console.error(e);
  }

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

ipcMain.handle("backend:url", () => BACKEND_URL);

ipcMain.handle("dialog:pick-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
