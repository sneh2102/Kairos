/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        panel: "#161b22",
        border: "#30363d",
        accent: "#58a6ff",
        primary: "#1f6feb",
        yes: "#3fb950",
        pass: "#238636",
        maybe: "#d29922",
        no: "#f85149",
        reject: "#da3633",
        muted: "#8b949e",
      },
    },
  },
  plugins: [],
};
