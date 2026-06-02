/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        dash: {
          cyan: "#0891b2",
          vio: "#7c3aed",
          mut: "#64748b",
        },
      },
      borderRadius: {
        dash: "14px",
      },
      fontFamily: {
        dash: [
          "Microsoft YaHei",
          "PingFang SC",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
