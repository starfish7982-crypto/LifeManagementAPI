import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, session, setUnauthorisedHandler } from "./api";
import { persistLang, setActiveLang, storedLang } from "./i18n";
import type { Lang } from "./i18n";

/* --------------------------------------------------------------------- language */

interface LanguageValue {
  lang: Lang;
  setLang: (next: Lang) => void;
}

const LanguageContext = createContext<LanguageValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(storedLang);

  const setLang = useCallback((next: Lang) => {
    // Two updates, deliberately. The module variable is what `t()` reads, including
    // from api.ts where there is no component tree to read context from; the React
    // state is what makes the tree re-render. Setting only one leaves half the app in
    // the old language until something else happens to redraw it.
    setActiveLang(next);
    persistLang(next);
    setLangState(next);
  }, []);

  useEffect(() => {
    setActiveLang(lang);
    persistLang(lang);
  }, [lang]);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside LanguageProvider");
  return ctx;
}

/* ---------------------------------------------------------------------- session */

interface SessionValue {
  username: string | null;
  /** undefined while the stored token is being checked, so the shell can render
   *  nothing rather than flashing the sign-in form at someone already signed in. */
  status: "checking" | "in" | "out";
  signIn: (username: string) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(session.username);
  const [status, setStatus] = useState<SessionValue["status"]>(
    session.token ? "checking" : "out",
  );

  const signIn = useCallback((next: string) => {
    setUsername(next);
    setStatus("in");
  }, []);

  const signOut = useCallback(() => {
    session.clear();
    setUsername(null);
    setStatus("out");
  }, []);

  // Any 401 from anywhere lands here. Registering it once, at the top, means no view
  // has to think about expiry.
  useEffect(() => {
    setUnauthorisedHandler(() => {
      setUsername(null);
      setStatus("out");
    });
  }, []);

  // A stored token may be expired. Verifying it once on boot means the first thing on
  // screen is either the app or the sign-in form, never a view that renders and then
  // collapses into an error.
  useEffect(() => {
    if (status !== "checking") return;
    let cancelled = false;
    api
      .me()
      .then((user) => {
        if (cancelled) return;
        setUsername(user.username);
        setStatus("in");
      })
      .catch(() => {
        if (!cancelled) setStatus("out");
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const value = useMemo(() => ({ username, status, signIn, signOut }), [username, status, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

/* ------------------------------------------------------------------------ toast */

const ToastContext = createContext<((message: string) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState("");

  const show = useCallback((next: string) => setMessage(next), []);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(""), 2200);
    return () => clearTimeout(timer);
  }, [message]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div id="toast" className={message ? "show" : ""}>
        {message}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (message: string) => void {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
