/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0a0908",
          900: "#100e0c",
          850: "#161310",
          800: "#1d1916",
          700: "#28221d",
          600: "#3a322a",
        },
        gold: {
          300: "#f0cd7c",
          400: "#e6b95a",
          500: "#d9a441",
          600: "#b8842e",
        },
        parchment: {
          100: "#f3ede1",
          300: "#cdc3b3",
          500: "#948a7a",
        },
      },
      fontFamily: {
        sans: ["'Space Grotesk'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
