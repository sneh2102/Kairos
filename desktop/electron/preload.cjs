// Renderer talks to the backend directly over fetch/WebSocket at a fixed
// localhost port, so no IPC bridge is needed for data — this just exposes
// the backend URL in case it ever needs to change (e.g. port conflict).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  getBackendUrl: () => ipcRenderer.invoke("backend:url"),
  pickFolder: () => ipcRenderer.invoke("dialog:pick-folder"),
  mobile: {
    start: () => ipcRenderer.invoke("mobile:start"),
    stop: () => ipcRenderer.invoke("mobile:stop"),
    status: () => ipcRenderer.invoke("mobile:status"),
    onStatus: (cb) => {
      const h = (_e, s) => cb(s);
      ipcRenderer.on("mobile:status", h);
      return () => ipcRenderer.removeListener("mobile:status", h);
    },
  },
});
