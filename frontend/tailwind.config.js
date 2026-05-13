export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bet: "#a78bfa",
        gate: "#facc15",
        conflict: "#ef4444",
        thought: "#34d399",
        firing: "#c084fc",
        codechange: "#60a5fa",
        doc: "#93c5fd",
      },
      animation: {
        "hot-pulse": "hot-pulse 2s ease-in-out infinite",
      },
      keyframes: {
        "hot-pulse": {
          "0%, 100%": { opacity: "0.6", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.08)" },
        },
      },
    },
  },
  plugins: [],
};
