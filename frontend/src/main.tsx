import React from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@radix-ui/themes";
import "@radix-ui/themes/styles.css";
import "./styles.css";
import "./workspace.css";
import App from "./App";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Theme
      appearance="dark"
      accentColor="gray"
      grayColor="gray"
      radius="medium"
    >
      <App />
    </Theme>
  </React.StrictMode>,
);
