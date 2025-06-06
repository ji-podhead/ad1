import type { Config } from "tailwindcss";

// @ts-ignore
const flowbite = require("flowbite/plugin");
// @ts-ignore
const tailwindcssAnimate = require("tailwindcss-animate");

export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {},
  },
  plugins: [
    tailwindcssAnimate,
    flowbite
  ],
} satisfies Config;
