/** Small shared helpers: escaping, formatting, toasts, modals, charts. */

/**
 * Escape a value for interpolation into HTML.
 *
 * Every view here builds markup as strings, so this is the single thing standing
 * between a list row and script injection. The data is the user's own, which lowers
 * the stakes but does not remove them: a value pasted from a website, or the same
 * database later shared with a second account, is not trusted input. Any `${}` holding
 * a value from the server goes through this.
 */
export const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/** Money as the API sends it: a decimal string, never a float. */
export function money(value) {
  const n = Number(value ?? 0);
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function money2(value) {
  const n = Number(value ?? 0);
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export const todayISO = () => new Date().toISOString().slice(0, 10);

export function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${y}/${m}/${d}`;
}

export function monthLabel(iso) {
  if (!iso) return "";
  const [y, m] = iso.slice(0, 7).split("-");
  return `${y}/${m}`;
}

let toastTimer;
export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

// ------------------------------------------------------------------------ modal

let closeModalFn = null;

export function openModal(html, { onSubmit } = {}) {
  closeModal();

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  document.body.appendChild(overlay);

  // Clicking the backdrop closes; clicking inside must not. Comparing the target to
  // the overlay itself is what distinguishes the two.
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal();
  });

  const onKey = (e) => {
    if (e.key === "Escape") closeModal();
  };
  document.addEventListener("keydown", onKey);

  const form = overlay.querySelector("form");
  if (form && onSubmit) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submit = form.querySelector('[type="submit"]');
      if (submit) submit.disabled = true;
      try {
        await onSubmit(new FormData(form), form);
      } finally {
        if (submit) submit.disabled = false;
      }
    });
  }

  overlay.querySelectorAll("[data-close]").forEach((b) =>
    b.addEventListener("click", () => closeModal()),
  );

  closeModalFn = () => {
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    closeModalFn = null;
  };

  const first = overlay.querySelector("input, select, textarea");
  if (first) first.focus();
  return overlay;
}

export function closeModal() {
  if (closeModalFn) closeModalFn();
}

/** Confirm before anything irreversible. `confirm()` is blocking and looks foreign. */
export function confirmDelete(what, onYes) {
  openModal(
    `<h2>刪除確認</h2>
     <p>確定要刪除「${esc(what)}」嗎？此動作無法復原。</p>
     <div class="modal-actions">
       <button type="button" class="btn" data-close>取消</button>
       <button type="button" class="btn danger" id="confirm-yes">刪除</button>
     </div>`,
  );
  document.getElementById("confirm-yes").addEventListener("click", async () => {
    closeModal();
    await onYes();
  });
}

// ----------------------------------------------------------------------- charts

const PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#d03b3b", "#898781"];
export const colourFor = (i) => PALETTE[i % PALETTE.length];

/** Donut of category totals. Hand-rolled SVG rather than a charting dependency:
 *  two shapes and a legend do not justify 60kB and a build step. */
export function donutSVG(slices) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return '<div class="empty-note">沒有資料</div>';

  const R = 60;
  const C = 2 * Math.PI * R;
  let offset = 0;

  const rings = slices
    .map((s, i) => {
      const len = (s.value / total) * C;
      const dash = `${len} ${C - len}`;
      const circle = `<circle cx="80" cy="80" r="${R}" fill="none" stroke="${colourFor(i)}"
        stroke-width="26" stroke-dasharray="${dash}" stroke-dashoffset="${-offset}"
        transform="rotate(-90 80 80)"><title>${esc(s.label)}: ${money(s.value)}</title></circle>`;
      offset += len;
      return circle;
    })
    .join("");

  const legend = slices
    .map(
      (s, i) =>
        `<div class="legend-row"><span class="dot" style="background:${colourFor(i)}"></span>
         <span>${esc(s.label)}</span><span class="right">${money(s.value)}</span></div>`,
    )
    .join("");

  return `<div class="grid-2">
      <div class="chart-box"><svg viewBox="0 0 160 160">${rings}</svg></div>
      <div class="legend">${legend}</div>
    </div>`;
}

/** Net worth over time. */
export function lineChartSVG(points) {
  if (points.length < 2) return '<div class="empty-note">至少需要兩個月的資料才能畫趨勢</div>';

  const W = 520;
  const H = 180;
  const PAD = 34;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would divide by zero; giving it a range of 1 draws a level line.
  const span = max - min || 1;

  const x = (i) => PAD + (i * (W - PAD * 2)) / (points.length - 1);
  const y = (v) => H - PAD - ((v - min) / span) * (H - PAD * 2);

  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
  const dots = points
    .map(
      (p, i) =>
        `<circle cx="${x(i)}" cy="${y(p.value)}" r="3.5" fill="var(--accent)">
           <title>${esc(p.label)}: ${money(p.value)}</title></circle>`,
    )
    .join("");
  const labels = points
    .map(
      (p, i) =>
        `<text x="${x(i)}" y="${H - 10}" font-size="10" fill="var(--muted)"
           text-anchor="middle">${esc(p.label)}</text>`,
    )
    .join("");

  return `<div class="chart-box"><svg viewBox="0 0 ${W} ${H}">
      <line x1="${PAD}" y1="${H - PAD}" x2="${W - PAD}" y2="${H - PAD}"
            stroke="var(--baseline)" stroke-width="1"/>
      <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>
      ${dots}${labels}
    </svg></div>`;
}
