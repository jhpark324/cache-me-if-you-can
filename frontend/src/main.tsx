import React from "react";
import { createRoot } from "react-dom/client";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import koKR from "@astryxdesign/core/locales/ko-KR.generated.js";
import { Theme } from "@astryxdesign/core/theme";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import { cacheMeTheme } from "./theme/cache-me.js";
import "./theme/cache-me.css";
import "./styles.css";
import "./workspace.css";
import "./RecordBrowser.css";
import "./ArticleWorkspace.css";
import "./SearchLoading.css";
import "./Graph.css";
import App from "./App";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Theme theme={cacheMeTheme} mode="dark">
      <InternationalizationProvider locale="ko-KR" messages={{ "ko-KR": koKR }}>
        <App />
      </InternationalizationProvider>
    </Theme>
  </React.StrictMode>,
);
