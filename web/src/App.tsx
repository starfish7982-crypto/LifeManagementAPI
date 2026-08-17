import { useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { LanguageSwitch } from "./components/LanguageSwitch";
import { Field, Modal } from "./components/Modal";
import { ApiError, api } from "./lib/api";
import { useLanguage, useSession, useToast } from "./lib/context";
import { t } from "./lib/i18n";
import type { MessageKey } from "./lib/i18n";
import { Assets } from "./views/Assets";
import { Dashboard } from "./views/Dashboard";
import { Grocery } from "./views/Grocery";
import { Ideas } from "./views/Ideas";
import { Lists } from "./views/Lists";
import { Reminders } from "./views/Reminders";
import { Settings } from "./views/Settings";
import { Today } from "./views/Today";
import { Travel } from "./views/Travel";

type ViewName =
  | "today"
  | "dashboard"
  | "assets"
  | "lists"
  | "grocery"
  | "travel"
  | "ideas"
  | "reminders"
  | "settings";

const NAV: { name: ViewName; icon: string; label: MessageKey }[] = [
  { name: "today", icon: "✅", label: "nav_today" },
  { name: "dashboard", icon: "📈", label: "nav_dashboard" },
  { name: "assets", icon: "💰", label: "nav_assets" },
  { name: "lists", icon: "📋", label: "nav_lists" },
  { name: "grocery", icon: "🛒", label: "nav_grocery" },
  { name: "travel", icon: "✈️", label: "nav_travel" },
  { name: "ideas", icon: "💡", label: "nav_ideas" },
  { name: "reminders", icon: "⏰", label: "nav_reminders" },
  { name: "settings", icon: "⚙️", label: "nav_settings" },
];

export function App() {
  const { status } = useSession();

  // Nothing while the stored token is being checked. Rendering the sign-in form first
  // would flash it at someone who is already signed in.
  if (status === "checking") return null;
  if (status === "out") return <AuthScreen />;
  return <Shell />;
}

function Shell() {
  const { username, signOut } = useSession();
  const { lang } = useLanguage();
  const [view, setView] = useState<ViewName>("today");
  const [changingPassword, setChangingPassword] = useState(false);

  return (
    <div className="layout">
      {/* The bottom bar holds nine destinations on a phone and has no room left for
          account controls, so they live up here instead. `.mobile-top` is
          `display: none` above 768px, which is why this is not a duplicate of the
          sidebar footer rather than a replacement for it. */}
      <header className="mobile-top">
        <div className="brand">🌱 LifeManagement</div>
        <div className="mobile-account">
          <LanguageSwitch current={lang} />
          <button type="button" className="linklike" onClick={() => setChangingPassword(true)}>
            {t("change_password")}
          </button>
          <button type="button" className="linklike" onClick={signOut}>
            {t("sign_out")}
          </button>
        </div>
      </header>

      <nav className="sidebar" aria-label={t("nav_aria")}>
        <div className="brand desktop-only">🌱 LifeManagement</div>

        {NAV.map((item) => (
          <button
            key={item.name}
            type="button"
            className={`nav-btn ${view === item.name ? "active" : ""}`}
            aria-current={view === item.name ? "page" : undefined}
            onClick={() => setView(item.name)}
          >
            <span className="nav-ico" aria-hidden="true">
              {item.icon}
            </span>
            <span className="nav-lbl">{t(item.label)}</span>
          </button>
        ))}

        <div className="sidebar-footer">
          <LanguageSwitch current={lang} />
          <div className="signed-in-as">{username}</div>
          <button type="button" className="linklike" onClick={() => setChangingPassword(true)}>
            {t("change_password")}
          </button>
          <button type="button" className="linklike" onClick={signOut}>
            {t("sign_out")}
          </button>
        </div>
      </nav>

      <main className="content">
        {/* `key` remounts the view on a language change, so a screen that formatted its
            strings at render time picks up the new locale instead of keeping the old. */}
        <ViewBody view={view} lang={lang} onOpenReminders={() => setView("reminders")} />
      </main>

      {changingPassword && <PasswordModal onClose={() => setChangingPassword(false)} />}
    </div>
  );
}

function ViewBody({
  view,
  lang,
  onOpenReminders,
}: {
  view: ViewName;
  lang: string;
  onOpenReminders: () => void;
}) {
  switch (view) {
    case "dashboard":
      return <Dashboard key={lang} onOpenReminders={onOpenReminders} />;
    case "assets":
      return <Assets key={lang} />;
    case "lists":
      return <Lists key={lang} />;
    case "grocery":
      return <Grocery key={lang} />;
    case "travel":
      return <Travel key={lang} />;
    case "ideas":
      return <Ideas key={lang} />;
    case "reminders":
      return <Reminders key={lang} />;
    case "settings":
      return <Settings key={lang} />;
    case "today":
      return <Today key={lang} />;
  }
}

function PasswordModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <Modal
      title={t("change_password")}
      onClose={onClose}
      busy={busy}
      onSubmit={async (form) => {
        setBusy(true);
        setError(null);
        try {
          await api.changePassword(String(form.get("current")), String(form.get("next")));
          toast(t("password_changed"));
          onClose();
        } catch (err) {
          setError(
            err instanceof ApiError && err.status === 401
              ? t("wrong_current_password")
              : t("save_failed"),
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <p className="auth-error">{error}</p>}
      <Field label={t("current_password")}>
        <input name="current" type="password" autoComplete="current-password" required />
      </Field>
      <Field label={t("new_password")}>
        <input
          name="next"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
        />
      </Field>
    </Modal>
  );
}
