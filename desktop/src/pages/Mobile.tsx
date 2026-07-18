import { useEffect, useState } from "react";
import QRCode from "qrcode";

const STEPS: Record<MobileStatus["phase"], string> = {
  idle: "Not running",
  "starting-tunnel": "Opening Cloudflare tunnel to your backend…",
  "starting-expo": "Tunnel up — starting Expo (this can take ~30s the first time)…",
  ready: "Ready — scan the QR with Expo Go",
  error: "Something went wrong",
};

export default function Mobile() {
  const bridge = window.desktop?.mobile;
  const [status, setStatus] = useState<MobileStatus>({ phase: "idle", backendUrl: null, expoUrl: null, error: null });
  const [qr, setQr] = useState<string | null>(null);

  useEffect(() => {
    if (!bridge) return;
    bridge.status().then(setStatus);
    return bridge.onStatus(setStatus);
  }, [bridge]);

  useEffect(() => {
    if (status.expoUrl) QRCode.toDataURL(status.expoUrl, { width: 260, margin: 1 }).then(setQr);
    else setQr(null);
  }, [status.expoUrl]);

  if (!bridge) {
    return <div className="text-sm text-muted">The mobile bridge is only available in the desktop app.</div>;
  }

  const busy = status.phase === "starting-tunnel" || status.phase === "starting-expo";
  const running = busy || status.phase === "ready";

  return (
    <div className="flex flex-col gap-5 max-w-xl">
      <div>
        <h1 className="text-lg font-semibold text-fg">Mobile</h1>
        <p className="text-sm text-muted">
          Use Kairos on your phone from anywhere. Start the bridge, then scan the QR with the{" "}
          <span className="text-fg">Expo Go</span> app. Works on any network — no same-WiFi needed.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                status.phase === "ready" ? "bg-good" : status.phase === "error" ? "bg-bad" : busy ? "bg-accent animate-pulse" : "bg-muted"
              }`}
            />
            <span className="text-sm text-fg">{STEPS[status.phase]}</span>
          </div>
          {running ? (
            <button
              onClick={() => bridge.stop()}
              className="rounded-full px-4 py-2 text-sm border border-border text-fg-soft hover:bg-subtle"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={() => bridge.start()}
              className="rounded-full px-4 py-2 text-sm bg-accent text-on-accent font-medium hover:opacity-90"
            >
              Start mobile
            </button>
          )}
        </div>

        {status.phase === "error" && status.error && (
          <div className="rounded-lg bg-bad/10 text-bad text-sm px-3 py-2">{status.error}</div>
        )}

        {qr && (
          <div className="flex flex-col items-center gap-3 pt-1">
            <img src={qr} alt="Expo Go QR code" className="rounded-xl bg-white p-3" width={260} height={260} />
            <p className="text-xs text-muted text-center">
              Open <span className="text-fg">Expo Go</span> and scan this (first load takes ~20–30s while Metro
              bundles). Or enter the URL manually:
            </p>
            <code className="text-xs text-fg-soft break-all text-center">{status.expoUrl}</code>
          </div>
        )}

        {status.backendUrl && (
          <p className="text-xs text-muted break-all">
            Backend tunnel: <span className="text-fg-soft">{status.backendUrl}</span>
          </p>
        )}
      </div>
    </div>
  );
}
