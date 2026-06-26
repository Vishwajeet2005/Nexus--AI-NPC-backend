/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm light base — clean, airy, human-like
        base: "#fafafa",
        panel: "#ffffff",
        raised: "#f4f4f5",
        hover: "#f4f4f5",
        border: "#e4e4e7",
        "border-light": "#f4f4f5",

        // Accent — a warm, approachable brand color
        blue: {
          DEFAULT: "#2563eb",
          dim: "#2563eb18",
          soft: "#2563eb30",
        },

        // Text — dark, organic ink colors for readability
        ink: "#18181b",
        "ink-2": "#52525b",
        "ink-3": "#a1a1aa",

        // Semantic colors
        green:  "#10b981",
        red:    "#ef4444",
        yellow: "#f59e0b",
        purple: "#8b5cf6",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", "14px"],
      },
      boxShadow: {
        sm:  "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
        md:  "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
        glow: "0 0 0 3px rgba(37, 99, 235, 0.2)",
      },
    },
  },
  plugins: [],
};
