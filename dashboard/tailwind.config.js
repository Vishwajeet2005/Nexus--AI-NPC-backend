/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm dark base — not pure zinc, has a touch of warmth
        base: "#0f0f11",
        panel: "#161618",
        raised: "#1c1c1f",
        hover: "#222226",
        border: "#2a2a2e",
        "border-light": "#333338",

        // Accent — a considered blue, not a generic brand color
        blue: {
          DEFAULT: "#4c7cf4",
          dim: "#4c7cf418",
          soft: "#4c7cf430",
        },

        // Text — warm off-whites, not pure white
        ink: "#eeeef0",
        "ink-2": "#9898a6",
        "ink-3": "#5c5c6e",

        // Semantic colors
        green:  "#3ecf8e",
        red:    "#f16a50",
        yellow: "#f5a623",
        purple: "#9d7aea",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", "14px"],
      },
      boxShadow: {
        sm:  "0 1px 2px rgba(0,0,0,0.5)",
        md:  "0 2px 8px rgba(0,0,0,0.4)",
        glow: "0 0 0 3px rgba(76,124,244,0.2)",
      },
    },
  },
  plugins: [],
};
