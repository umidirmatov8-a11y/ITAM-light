import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/home.css";
import "./styles/screens.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

document.documentElement.dataset.theme = "amber";
document.documentElement.dataset.anim = "on";
document.documentElement.dataset.scanlines = "on";

const compact = window.location.hash === "#compact";
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App compact={compact} />
  </StrictMode>,
);
