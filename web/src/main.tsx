import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppRoot } from "./app/AppRoot";
import { createComposition } from "./app/composition";
import { appMode } from "./config/mode";

const rootElement = document.getElementById("root");

if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <AppRoot composition={createComposition(appMode())} />
    </StrictMode>,
  );
}
