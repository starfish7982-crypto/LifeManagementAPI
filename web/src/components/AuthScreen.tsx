import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, api } from "../lib/api";
import { useLanguage, useSession } from "../lib/context";
import { t } from "../lib/i18n";
import { LanguageSwitch } from "./LanguageSwitch";

export function AuthScreen() {
  const { signIn } = useSession();
  const { lang } = useLanguage();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Starts closed and opens only on an explicit yes from the server. The alternative
  // default flashes a "create an account" link on every load and then withdraws it,
  // and on a closed instance that link was never going to work.
  const [canRegister, setCanRegister] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .authConfig()
      .then((cfg) => {
        if (live) setCanRegister(cfg.registration_open);
      })
      // An unreachable server is not a reason to offer a sign-up that cannot succeed.
      // Sign-in still renders, and says what went wrong when it is attempted.
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  const registering = mode === "register";

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const username = String(form.get("username") ?? "").trim();
    const password = String(form.get("password") ?? "");

    setBusy(true);
    try {
      if (registering) await api.register(username, password);
      await api.login(username, password);
      signIn(username);
    } catch (err) {
      // 401 here is a rejected credential, not an expired session — api.ts only routes
      // the latter through the global handler, so this branch owns the wording.
      //
      // That wording is mode-aware: "wrong password, try registering" is unhelpful
      // advice to someone who is already on the registration form.
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError(t(registering ? "already_registered" : "bad_credentials"));
        } else if (err.status === 422 && err.detail.includes("username")) {
          setError(t("bad_username"));
        } else {
          setError(err.detail);
        }
      } else {
        setError(t("network_error"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      {/* method="post" is not there because this form is ever submitted natively —
          React intercepts it. It is there for when the bundle has NOT loaded: a form
          with no method defaults to GET, and a native submit would put the password in
          the URL, the address bar, the history, and any Referer header sent next.
          Defaults matter most exactly when the code you were relying on did not run. */}
      <form className="auth-card" method="post" action="" onSubmit={onSubmit} autoComplete="on">
        <div className="auth-brand">🌱 LifeManagement</div>
        <p className="auth-sub">{t(registering ? "auth_sub_register" : "auth_sub_login")}</p>

        <div className="field">
          <label htmlFor="auth-username">{t("username")}</label>
          {/* The autocomplete hints let a password manager fill and, more importantly,
              save these. A generated password nobody can remember is only usable if
              the browser offers to keep it. */}
          <input id="auth-username" name="username" type="text" autoComplete="username" minLength={3} maxLength={60} required />
        </div>

        <div className="field">
          <label htmlFor="auth-password">{t("password")}</label>
          <input
            id="auth-password"
            name="password"
            type="password"
            /* Remounted when the mode changes, so the browser is asked to save a new
               password rather than to fill the old one. */
            key={mode}
            autoComplete={registering ? "new-password" : "current-password"}
            minLength={8}
            required
          />
        </div>

        {error && <p className="auth-error">{error}</p>}

        <button type="submit" className="btn primary auth-submit" disabled={busy}>
          {busy ? t("please_wait") : t(registering ? "register" : "login")}
        </button>

        {canRegister && (
          <p className="auth-toggle">
            <span>{t(registering ? "have_account" : "no_account")}</span>{" "}
            <button
              type="button"
              className="linklike"
              onClick={() => {
                setMode(registering ? "login" : "register");
                setError(null);
              }}
            >
              {t(registering ? "login" : "register")}
            </button>
          </p>
        )}

        <LanguageSwitch className="auth-lang" current={lang} />
      </form>
    </div>
  );
}
