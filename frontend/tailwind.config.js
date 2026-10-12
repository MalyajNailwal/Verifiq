/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
      },
      colors: {
        paper: "#f4f1ea",
        ink: "#1a1710",
        rule: "#d8d2c4",
        stamp: "#b3372b",
        verify: "#2d5a3d",
        amber: {"400": "#d9a441"},
      },
    },
  },
  plugins: [],
};
