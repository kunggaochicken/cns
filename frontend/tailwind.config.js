/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bet: "#a855f7",
        gate: "#fbbf24",
        conflict: "#f87171",
        thought: "#4ade80",
        firing: "#ec4899",
        codechange: "#60a5fa",
        doc: "#818cf8",
        hotspot: "#f97316",
      },
    },
  },
  plugins: [],
};
