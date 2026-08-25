/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Light theme surfaces: 950 = page background (white), descending
        // numbers get progressively darker/greyer for cards, inputs, borders.
        base: {
          950: "#FFFFFF",
          900: "#F3F5FA",
          800: "#EAEDF5",
          700: "#DEE2ED",
          600: "#C5CBDA",
        },
        // quest1's orange accent, kept under the "amber" key so every
        // existing amber-400/500/600 class in the components repaints
        // automatically without touching those files.
        amber: {
          400: "#F4894F",
          500: "#EE6C2E",
          600: "#C8501C",
        },
        found: "#1E9D63",
        miss: "#D6483C",
        // Tailwind's default "neutral" scale is inverted here on purpose:
        // in the old dark theme, neutral-50/100 meant "brightest/whitest
        // text". On a white page that same brightest-emphasis text needs
        // to be the darkest navy, so 50 -> darkest, 950 -> lightest.
        // This lets every existing text-neutral-* class in every
        // component repaint correctly for light mode with zero edits
        // to those files.
        neutral: {
          50: "#0A1330",
          100: "#12213F",
          200: "#1C2C4A",
          300: "#334155",
          400: "#475569",
          500: "#5B6472",
          600: "#7C8698",
          700: "#9CA6B8",
          800: "#C7CEDA",
          900: "#E7EAF1",
          950: "#F5F6FA",
        },
      },
      fontFamily: {
        display: ["\"Space Grotesk\"", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["\"JetBrains Mono\"", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        sprockets:
          "radial-gradient(circle, rgba(238,108,46,0.35) 1.5px, transparent 1.5px)",
      },
    },
  },
  plugins: [],
};