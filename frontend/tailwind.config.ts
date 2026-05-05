import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        pretendard: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif",
        ],
      },
      colors: {
        "header-navy": "#1E293B",
        "primary-navy": "#002045",
        "panel-bg": "#FAF9FD",
        "page-bg": "#F4F3F7",
        "border-default": "#E2E8F0",
        "text-primary": "#1A1C1E",
        "text-secondary": "#43474E",
        "success-green": "#34D399",
        "warning-bg": "#FEE2E2",
        "warning-border": "#F65746",
        "warning-text": "#991B1B",
        "guide-bg": "#E0F2FE",
        "guide-border": "#9FCAFF",
      },
    },
  },
  plugins: [],
};

export default config;
