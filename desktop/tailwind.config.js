/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // semantic tokens — resolve to CSS variables (light/dark) in index.css
        bg: "var(--bg)",
        surface: "var(--surface)",
        panel: "var(--surface)", // legacy alias
        subtle: "var(--subtle)",
        track: "var(--track)",
        border: "var(--border)",
        edge: "var(--edge)",
        fg: "var(--fg)",
        "fg-soft": "var(--fg-soft)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "on-accent": "var(--on-accent)",
        primary: "var(--accent)", // legacy alias
        good: "var(--good)",
        warn: "var(--warn)",
        bad: "var(--bad)",
        // legacy status aliases used across pages
        yes: "var(--good)",
        pass: "var(--good)",
        maybe: "var(--warn)",
        no: "var(--bad)",
        reject: "var(--bad)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        pop: "var(--shadow-pop)",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
