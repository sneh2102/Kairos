/// <reference types="vite/client" />

interface Window {
  desktop?: {
    getBackendUrl: () => Promise<string>;
    pickFolder: () => Promise<string | null>;
  };
}
