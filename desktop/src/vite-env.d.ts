/// <reference types="vite/client" />

type MobileStatus = {
  phase: "idle" | "starting-tunnel" | "starting-expo" | "ready" | "error";
  backendUrl: string | null;
  expoUrl: string | null;
  error: string | null;
};

type WebBridgeStatus = {
  phase: "idle" | "starting" | "ready" | "error";
  url: string | null;
  error: string | null;
};

interface Window {
  desktop?: {
    getBackendUrl: () => Promise<string>;
    pickFolder: () => Promise<string | null>;
    mobile: {
      start: () => Promise<MobileStatus>;
      stop: () => Promise<MobileStatus>;
      status: () => Promise<MobileStatus>;
      onStatus: (cb: (s: MobileStatus) => void) => () => void;
    };
    web: {
      start: () => Promise<WebBridgeStatus>;
      stop: () => Promise<WebBridgeStatus>;
      status: () => Promise<WebBridgeStatus>;
      token: () => Promise<string>;
      setToken: (token: string) => Promise<string>;
      onStatus: (cb: (s: WebBridgeStatus) => void) => () => void;
    };
  };
}
