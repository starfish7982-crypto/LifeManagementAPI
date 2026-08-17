import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { LanguageProvider, SessionProvider, ToastProvider } from "./lib/context";

import "./styles/style.css";
import "./styles/auth.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  // StrictMode double-invokes effects in development on purpose. It is noisy, and it
  // is the reason `useResource` had to drop stale responses rather than assume each
  // effect runs once — a bug that would otherwise only appear under a slow network.
  <StrictMode>
    <LanguageProvider>
      <ToastProvider>
        <SessionProvider>
          <App />
        </SessionProvider>
      </ToastProvider>
    </LanguageProvider>
  </StrictMode>,
);
