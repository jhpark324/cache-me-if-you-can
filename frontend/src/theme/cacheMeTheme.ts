import { defineTheme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";

const koreanFont =
  'Pretendard, -apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif';

export const cacheMeTheme = defineTheme({
  name: "cache-me",
  extends: neutralTheme,
  typography: {
    body: {
      family: "Pretendard",
      fallbacks: '-apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif',
    },
    heading: {
      family: "Pretendard",
      fallbacks: '-apple-system, BlinkMacSystemFont, "Malgun Gothic", sans-serif',
    },
  },
  tokens: {
    "--font-family-body": koreanFont,
    "--font-family-heading": koreanFont,
    "--color-background-body": ["#ffffff", "#000000"],
    "--color-background-surface": ["#f5f5f5", "#111111"],
    "--color-background-card": ["#ffffff", "#171717"],
    "--color-text-primary": ["#111111", "#ffffff"],
    "--color-text-secondary": ["#4b4b4b", "#b8b8b8"],
    "--color-accent": ["#a54f1c", "#f2b786"],
    "--color-accent-muted": ["#f8e6d7", "#3b271b"],
    "--color-on-accent": ["#ffffff", "#25170c"],
    "--color-text-accent": ["#a54f1c", "#f2b786"],
    "--color-icon-accent": ["#a54f1c", "#f2b786"],
  },
});
