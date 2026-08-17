import { useLanguage } from "../lib/context";
import type { Lang } from "../lib/i18n";

const OPTIONS: { code: Lang; label: string }[] = [
  { code: "zh", label: "中文" },
  { code: "en", label: "EN" },
];

export function LanguageSwitch({ className = "", current }: { className?: string; current: Lang }) {
  const { setLang } = useLanguage();
  return (
    <div className={`lang-switch ${className}`} role="group" aria-label="Language">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          type="button"
          className={`lang-btn ${o.code === current ? "active" : ""}`}
          aria-pressed={o.code === current}
          onClick={() => setLang(o.code)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
