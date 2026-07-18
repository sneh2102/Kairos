// Your PC's backend, exposed via Cloudflare Tunnel.
// Both values below are overwritten by the desktop app every time you start
// the mobile bridge: API_BASE gets the fresh trycloudflare.com URL, API_TOKEN
// gets this install's per-machine secret. Placeholders otherwise.
export const API_BASE = "https://example.trycloudflare.com";

// Shared secret the backend checks (x-api-token) on all tunnel traffic.
// Auto-filled to match the backend's per-install TUNNEL_TOKEN.
export const API_TOKEN = "";
