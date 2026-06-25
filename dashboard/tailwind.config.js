/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        nexus: {
          bg:      "#0a0a0f",
          surface: "#12121a",
          border:  "#1e1e2e",
          accent:  "#6c63ff",
          green:   "#4ade80",
          red:     "#f87171",
          yellow:  "#fbbf24",
          muted:   "#6b7280",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
