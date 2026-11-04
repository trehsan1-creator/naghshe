/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // SurveyPro engineering palette
        base: "#121417",
        panel: "#171A1F",
        panel2: "#1D2128",
        edge: "#252A33",
        ink: "#E6EDF5",
        muted: "#8A94A6",
        cyan: "#38BDF8",
        pink: "#F472B6",
        lime: "#A3E635",
        amber: "#FBBF24",
        danger: "#F87171",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
      },
      boxShadow: { panel: "0 1px 0 0 rgba(255,255,255,0.04) inset" },
    },
  },
  plugins: [],
};
