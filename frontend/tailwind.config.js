/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#0B0C0E",
          900: "#111318",
          800: "#181B21",
          700: "#22262E",
          600: "#2E333D",
        },
        amber: {
          400: "#F0B94F",
          500: "#E8A33D",
          600: "#C4832A",
        },
        found: "#6FCF97",
        miss: "#E1685B",
      },
      fontFamily: {
        display: ["\"Space Grotesk\"", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["\"JetBrains Mono\"", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        sprockets:
          "radial-gradient(circle, rgba(240,185,79,0.35) 1.5px, transparent 1.5px)",
      },
    },
  },
  plugins: [],
};
