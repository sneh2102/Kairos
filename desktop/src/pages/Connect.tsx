import { useState } from "react";
import { setBackendConfig } from "../lib/api";

// First screen for a standalone web deploy (no Electron bridge available).
// Get the URL + password from the desktop app's "Web access" panel (Mobile
// page), verify them, then store and reload — api.ts re-reads localStorage
// fresh on the next load.
export default function Connect() {
  const [url, setUrl] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    const base = url.trim().replace(/\/+$/, "");
    if (!base) return setError("Enter the backend link from the desktop app.");
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${base}/api/health`, { headers: { "x-api-token": password } });
      if (!res.ok) throw new Error(res.status === 401 ? "Wrong password." : `Backend returned ${res.status}.`);
      setBackendConfig(base, password); // reloads the page on success
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg">
      <div className="card p-6 w-full max-w-sm flex flex-col gap-4">
        <div>
          <h1 className="text-lg font-semibold text-fg">Connect to your backend</h1>
          <p className="text-sm text-muted mt-1">
            Open the desktop app, go to <span className="text-fg-soft">Mobile → Web access</span>, and start it to
            get a link and password.
          </p>
        </div>

        <div>
          <span className="label">Backend link</span>
          <input
            className="input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://xxxx.trycloudflare.com"
            autoCapitalize="none"
            autoCorrect="off"
          />
        </div>
        <div>
          <span className="label">Password</span>
          <input
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && connect()}
          />
        </div>

        {error && <div className="text-sm text-no">{error}</div>}

        <button className="btn-primary" onClick={connect} disabled={busy}>
          {busy ? "Connecting…" : "Connect"}
        </button>
      </div>
    </div>
  );
}
