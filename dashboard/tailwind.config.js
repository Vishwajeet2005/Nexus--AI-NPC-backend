/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#111118",
          raised: "#18181f",
          overlay: "#1e1e28",
        },
        border: {
          DEFAULT: "#27272f",
          subtle: "#1f1f27",
          strong: "#3f3f50",
        },
        accent: {
          DEFAULT: "#4f6ef7",
          hover:   "#6680ff",
          muted:   "#4f6ef720",
        },
        tx: {
          primary:  "#f4f4f6",
          secondary: "#8b8b9e",
          muted:    "#5a5a6e",
        },
        status: {
          green:  "#34d399",
          red:    "#f87171",
          yellow: "#fbbf24",
          blue:   "#60a5fa",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        card: "10px",
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(0 0 0 / 0.4), 0 1px 2px -1px rgb(0 0 0 / 0.4)",
        "card-hover": "0 4px 12px 0 rgb(0 0 0 / 0.5)",
      },
    },
  },
  plugins: [],
};
