/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        roboto: ["Roboto", "sans-serif"],
      },

      colors: {
        mainGreen: "#14AE5C",
        mainRed: "#FB0909",
        mainBlue: "#55B4C2",
      },
      screens: {
        sm: "360px", // мой самсунг 360х649, 480 обычно
        md: "768px",
        lg: "1024px",
        xl: "1440px",
      },
    },
  },
  plugins: [],
};
