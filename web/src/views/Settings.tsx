import { useState } from "react";
import type { FormEvent } from "react";

import { Field } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { ApiError, api } from "../lib/api";
import { useToast } from "../lib/context";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";

export function Settings() {
  const toast = useToast();
  const settings = useResource(() => api.settings());
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  const data = settings.data;

  const saveTelegram = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const token = String(form.get("telegram_bot_token") ?? "").trim();
    const chat = String(form.get("telegram_chat_id") ?? "").trim();

    // The token field is left blank when one is already stored — the API will not send
    // a secret back, so there is nothing to prefill it with. Omitting the key entirely
    // (rather than sending "") is what tells the PATCH to leave the stored one alone.
    const payload: { telegram_bot_token?: string; telegram_chat_id?: string } = {
      telegram_chat_id: chat,
    };
    if (token) payload.telegram_bot_token = token;

    try {
      await api.updateSettings(payload);
      toast(t("saved"));
      settings.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("save_failed"));
    }
  };

  const saveCalendar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    try {
      await api.updateSettings({
        google_calendar_ical_url: String(form.get("google_calendar_ical_url") ?? "").trim(),
      });
      toast(t("saved"));
      settings.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("save_failed"));
    }
  };

  return (
    <ViewFrame title={t("settings_title")} subtitle={t("settings_sub")} resources={[settings]}>
      {error && <div className="error-note">{error}</div>}

      <section className="card settings-card">
        <h2>{t("telegram_heading")}</h2>
        <div className="page-sub" style={{ marginBottom: 12 }}>
          <ol style={{ paddingLeft: 18 }}>
            <li>{t("telegram_step1")}</li>
            <li>{t("telegram_step2")}</li>
            <li>{t("telegram_step3")}</li>
          </ol>
        </div>

        <form onSubmit={saveTelegram} key={data?.updated_at ?? "empty"}>
          <Field label={t("bot_token")}>
            <input
              name="telegram_bot_token"
              type="password"
              autoComplete="off"
              maxLength={200}
              placeholder={data?.telegram_configured ? t("token_stored") : "123456:ABC-DEF..."}
            />
          </Field>
          <Field label={t("chat_id")}>
            <input
              name="telegram_chat_id"
              maxLength={64}
              placeholder="123456789"
              defaultValue={data?.telegram_chat_id ?? ""}
            />
          </Field>

          <div className="btn-row">
            <button type="submit" className="btn primary">
              {t("save")}
            </button>
            <button
              type="button"
              className="btn"
              disabled={testing || !data?.telegram_configured}
              onClick={async () => {
                setTesting(true);
                try {
                  const result = await api.testTelegram();
                  toast(result.detail);
                } finally {
                  setTesting(false);
                }
              }}
            >
              {testing ? t("please_wait") : t("send_test")}
            </button>
            {data?.telegram_configured && (
              <button
                type="button"
                className="btn danger"
                onClick={async () => {
                  await api.disconnectTelegram();
                  toast(t("disconnected"));
                  settings.reload();
                }}
              >
                {t("disconnect")}
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="card settings-card">
        <h2>{t("calendar_heading_settings")}</h2>
        <div className="page-sub" style={{ marginBottom: 12 }}>
          {t("calendar_help")}
        </div>

        <form onSubmit={saveCalendar} key={`cal-${data?.updated_at ?? "empty"}`}>
          <Field label={t("ical_url")}>
            <input
              name="google_calendar_ical_url"
              type="url"
              maxLength={500}
              placeholder="https://calendar.google.com/calendar/ical/.../basic.ics"
              defaultValue={data?.google_calendar_ical_url ?? ""}
            />
          </Field>
          <button type="submit" className="btn primary">
            {t("connect_calendar")}
          </button>
        </form>
      </section>

      <section className="card settings-card settings-guide">
        <h2>{t("daily_push_heading")}</h2>
        <div className="page-sub settings-guide-copy">
          <p>{t("daily_push_body")}</p>
          <p className="settings-command">POST /today/notify</p>
          <p className="settings-command">Authorization: Bearer &lt;token from /auth/login&gt;</p>
          <p>{t("daily_push_note")}</p>
        </div>
      </section>

      <section className="card settings-card settings-guide">
        <h2>{t("auto_push_heading")}</h2>
        <div className="page-sub settings-guide-copy">
          <p>{t("auto_push_body")}</p>
          <p>{t("auto_push_note")}</p>
        </div>
      </section>

      <section className="card settings-card settings-guide">
        <h2>{t("openclaw_heading")}</h2>
        <div className="page-sub settings-guide-copy"><p>{t("openclaw_body")}</p></div>
      </section>
    </ViewFrame>
  );
}
