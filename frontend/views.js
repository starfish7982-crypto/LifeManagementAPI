/** The five screens. Each exports `render(main)` and owns its own reloads. */

import { api } from "./api.js";
import {
  closeModal,
  confirmDelete,
  donutSVG,
  esc,
  fmtDate,
  lineChartSVG,
  money,
  money2,
  monthLabel,
  openModal,
  toast,
  todayISO,
} from "./ui.js";

/** Wrap a render so a failed fetch shows why instead of leaving a blank screen. */
async function guard(main, fn) {
  main.innerHTML = '<div class="loading">載入中…（服務閒置後首次載入需要 30-50 秒喚醒）</div>';
  try {
    await fn();
  } catch (err) {
    if (err.status === 401) return; // The shell is already showing the sign-in screen.
    main.innerHTML = `<div class="error-note">${esc(err.detail || err.message)}</div>`;
  }
}

const total = (snapshot) => Number(snapshot.total ?? 0);

// ----------------------------------------------------------------------- today

export function today(main, rerender) {
  return guard(main, async () => {
    const [data, todos] = await Promise.all([api.today(), api.todos()]);
    const open = todos.filter((t) => !t.done);
    const done = todos.filter((t) => t.done);

    const item = (t) => `
      <div class="todo-item">
        <input type="checkbox" data-todo="${t.id}" ${t.done ? "checked" : ""}>
        <div class="todo-body">
          <div class="todo-title" ${t.done ? 'style="opacity:.55;text-decoration:line-through"' : ""}>
            ${esc(t.title)}
          </div>
          ${t.due_date ? `<div class="todo-meta"><span class="todo-date">${fmtDate(t.due_date)}</span></div>` : ""}
        </div>
        <button class="btn tiny danger" data-del-todo="${t.id}">刪除</button>
      </div>`;

    main.innerHTML = `
      <h1 class="page-title">今日</h1>
      <div class="page-sub">${fmtDate(data.date)}</div>

      ${
        data.reminders_due.length
          ? `<div class="card">
              <h2>提醒</h2>
              ${data.reminders_due
                .map(
                  (r) => `<div class="due-item">
                    <span class="badge">${r.days_until_due === 0 ? "今天" : `還有 ${r.days_until_due} 天`}</span>
                    <div><div>${esc(r.title)}</div>
                    ${r.note ? `<div class="todo-note muted">${esc(r.note)}</div>` : ""}</div>
                  </div>`,
                )
                .join("")}
            </div>`
          : ""
      }

      ${
        data.calendar_events.length
          ? `<div class="card"><h2>行事曆</h2>
              ${data.calendar_events.map((e) => `<div class="due-item"><span>${esc(e.title)}</span></div>`).join("")}
            </div>`
          : ""
      }

      <div class="card">
        <div class="card-head-row"><h2>待辦</h2>
          <button class="btn" id="add-todo">新增</button></div>
        <div class="todo-section">
          ${open.length ? open.map(item).join("") : '<div class="empty-note">沒有未完成的待辦</div>'}
        </div>
        ${
          done.length
            ? `<div class="todo-section"><div class="page-sub">已完成 (${done.length})</div>
                ${done.map(item).join("")}</div>`
            : ""
        }
      </div>`;

    main.querySelectorAll("[data-todo]").forEach((box) =>
      box.addEventListener("change", async () => {
        await api.patchTodo(box.dataset.todo, { done: box.checked });
        toast("已更新");
        rerender();
      }),
    );

    main.querySelectorAll("[data-del-todo]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const title = btn.closest(".todo-item").querySelector(".todo-title").textContent.trim();
        confirmDelete(title, async () => {
          await api.deleteTodo(btn.dataset.delTodo);
          toast("已刪除");
          rerender();
        });
      }),
    );

    main.querySelector("#add-todo").addEventListener("click", () => {
      openModal(
        `<h2>新增待辦</h2>
         <form>
           <div class="field"><label for="t-title">標題</label>
             <input id="t-title" name="title" required maxlength="200"></div>
           <div class="field"><label for="t-due">到期日（可留空）</label>
             <input id="t-due" name="due_date" type="date"></div>
           <div class="modal-actions">
             <button type="button" class="btn" data-close>取消</button>
             <button type="submit" class="btn primary">新增</button>
           </div>
         </form>`,
        {
          onSubmit: async (form) => {
            await api.createTodo({
              title: form.get("title"),
              due_date: form.get("due_date") || null,
            });
            closeModal();
            toast("已新增");
            rerender();
          },
        },
      );
    });
  });
}

// ------------------------------------------------------------------- dashboard

export function dashboard(main) {
  return guard(main, async () => {
    const [snapshots, goal] = await Promise.all([api.snapshots(), api.goal()]);

    if (!snapshots.length) {
      main.innerHTML = `<h1 class="page-title">總覽</h1>
        <div class="empty-note">還沒有資產快照。到「資產」頁新增第一筆。</div>`;
      return;
    }

    // The API returns newest first; a time series has to read the other way.
    const chronological = [...snapshots].reverse();
    const latest = snapshots[0];
    const previous = snapshots[1];
    const delta = previous ? total(latest) - total(previous) : null;

    const byCategory = {};
    for (const it of latest.items) {
      byCategory[it.category] = (byCategory[it.category] || 0) + Number(it.amount);
    }
    const slices = Object.entries(byCategory)
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);

    const progress = goal ? Math.min(100, (total(latest) / Number(goal.amount)) * 100) : 0;

    main.innerHTML = `
      <h1 class="page-title">總覽</h1>
      <div class="page-sub">${monthLabel(latest.month)}</div>

      <div class="card">
        <div class="card-head-row">
          <div>
            <div class="hero-num">${money(total(latest))}</div>
            ${
              delta === null
                ? ""
                : `<div class="delta" style="color:${delta >= 0 ? "var(--good)" : "var(--bad)"}">
                     ${delta >= 0 ? "▲" : "▼"} ${money(Math.abs(delta))}
                     <span class="delta-note">較 ${monthLabel(previous.month)}</span>
                   </div>`
            }
          </div>
          ${
            goal
              ? `<div class="goal-mini">
                  <div class="goal-mini-title">${esc(goal.purpose)}</div>
                  <div class="goal-progress">
                    <div class="goal-bar"><div class="goal-fill" style="width:${progress}%"></div></div>
                    <div class="goal-stats">${money(total(latest))} / ${money(goal.amount)}
                      （${progress.toFixed(0)}%）</div>
                  </div>
                  ${goal.next_step ? `<div class="goal-stats muted">下一步：${esc(goal.next_step)}</div>` : ""}
                </div>`
              : ""
          }
        </div>
      </div>

      <div class="card"><h2>趨勢</h2>
        ${lineChartSVG(chronological.map((s) => ({ label: monthLabel(s.month), value: total(s) })))}
      </div>

      <div class="card"><h2>類別分佈</h2>${donutSVG(slices)}</div>`;
  });
}

// ------------------------------------------------------------------------ assets

function snapshotForm(snapshot, categories) {
  const row = (it = {}) => `
    <tr>
      <td><input name="name" value="${esc(it.name || "")}" placeholder="名稱" required></td>
      <td><input name="category" value="${esc(it.category || "")}" list="cat-list"
                 placeholder="類別" required></td>
      <td><input name="amount" value="${esc(it.amount || "")}" type="number" step="0.01"
                 placeholder="金額" required class="right"></td>
      <td><button type="button" class="btn tiny danger" data-drop-row>×</button></td>
    </tr>`;

  return `<h2>${snapshot ? "編輯" : "新增"}資產快照</h2>
    <form>
      <datalist id="cat-list">${categories.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>
      <div class="field"><label for="s-month">月份</label>
        <input id="s-month" name="month" type="month" required
               value="${snapshot ? esc(snapshot.month.slice(0, 7)) : todayISO().slice(0, 7)}"></div>
      <div class="field"><label for="s-note">備註</label>
        <input id="s-note" name="note" maxlength="500" value="${esc(snapshot?.note || "")}"></div>
      <div class="table-wrap"><table class="list-table"><tbody id="item-rows">
        ${(snapshot?.items?.length ? snapshot.items : [{}]).map(row).join("")}
      </tbody></table></div>
      <button type="button" class="btn tiny" id="add-row">新增項目</button>
      <div class="modal-actions">
        <button type="button" class="btn" data-close>取消</button>
        <button type="submit" class="btn primary">儲存</button>
      </div>
    </form>`;
}

function collectItems(form) {
  return [...form.querySelectorAll("#item-rows tr")].map((tr) => ({
    name: tr.querySelector('[name="name"]').value,
    category: tr.querySelector('[name="category"]').value,
    // Sent as a string. The API stores Numeric(14,2); routing the value through a JS
    // number on the way out would reintroduce the float error the column exists to avoid.
    amount: tr.querySelector('[name="amount"]').value,
  }));
}

export function assets(main, rerender) {
  return guard(main, async () => {
    const [snapshots, categories, goal] = await Promise.all([
      api.snapshots(),
      api.categories(),
      api.goal(),
    ]);

    main.innerHTML = `
      <h1 class="page-title">資產</h1>
      <div class="card">
        <div class="card-head-row"><h2>目標</h2>
          <button class="btn" id="edit-goal">${goal ? "編輯" : "設定"}</button></div>
        ${
          goal
            ? `<div>${esc(goal.purpose)} — <strong>${money(goal.amount)}</strong></div>
               ${goal.next_step ? `<div class="muted">下一步：${esc(goal.next_step)}</div>` : ""}`
            : '<div class="empty-note">尚未設定目標</div>'
        }
      </div>

      <div class="card">
        <div class="card-head-row"><h2>每月快照</h2>
          <button class="btn" id="add-snapshot">新增</button></div>
        ${
          snapshots.length
            ? snapshots
                .map(
                  (s) => `<div class="asset-row">
                    <div><strong>${monthLabel(s.month)}</strong>
                      <span class="muted">（${s.items.length} 項）</span>
                      ${s.note ? `<div class="muted">${esc(s.note)}</div>` : ""}</div>
                    <div class="right"><strong>${money(s.total)}</strong></div>
                    <div class="row-actions">
                      <button class="btn tiny" data-edit="${s.id}">編輯</button>
                      <button class="btn tiny danger" data-del="${s.id}">刪除</button>
                    </div>
                  </div>`,
                )
                .join("")
            : '<div class="empty-note">還沒有快照</div>'
        }
      </div>`;

    main.querySelector("#edit-goal").addEventListener("click", () => {
      openModal(
        `<h2>資產目標</h2>
         <form>
           <div class="field"><label for="g-amount">目標金額 (USD)</label>
             <input id="g-amount" name="amount" type="number" step="0.01" min="0.01" required
                    value="${esc(goal?.amount || "")}"></div>
           <div class="field"><label for="g-purpose">用途</label>
             <input id="g-purpose" name="purpose" required maxlength="200"
                    value="${esc(goal?.purpose || "")}"></div>
           <div class="field"><label for="g-next">下一步</label>
             <input id="g-next" name="next_step" maxlength="200"
                    value="${esc(goal?.next_step || "")}"></div>
           <div class="modal-actions">
             <button type="button" class="btn" data-close>取消</button>
             <button type="submit" class="btn primary">儲存</button>
           </div>
         </form>`,
        {
          onSubmit: async (form) => {
            await api.setGoal({
              amount: form.get("amount"),
              purpose: form.get("purpose"),
              next_step: form.get("next_step") || null,
            });
            closeModal();
            toast("已儲存");
            rerender();
          },
        },
      );
    });

    const openSnapshotForm = (snapshot) => {
      const overlay = openModal(snapshotForm(snapshot, categories), {
        onSubmit: async (form, formEl) => {
          const payload = {
            month: `${form.get("month")}-01`,
            note: form.get("note") || null,
            items: collectItems(formEl),
          };
          if (snapshot) await api.replaceSnapshot(snapshot.id, payload);
          else await api.createSnapshot(payload);
          closeModal();
          toast("已儲存");
          rerender();
        },
      });

      const rows = overlay.querySelector("#item-rows");
      const wireDrop = (btn) =>
        btn.addEventListener("click", () => {
          // Never remove the last row: an empty tbody gives no way back to a form.
          if (rows.children.length > 1) btn.closest("tr").remove();
        });
      rows.querySelectorAll("[data-drop-row]").forEach(wireDrop);

      overlay.querySelector("#add-row").addEventListener("click", () => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><input name="name" placeholder="名稱" required></td>
          <td><input name="category" list="cat-list" placeholder="類別" required></td>
          <td><input name="amount" type="number" step="0.01" placeholder="金額" required class="right"></td>
          <td><button type="button" class="btn tiny danger" data-drop-row>×</button></td>`;
        rows.appendChild(tr);
        wireDrop(tr.querySelector("[data-drop-row]"));
        tr.querySelector("input").focus();
      });
    };

    main.querySelector("#add-snapshot").addEventListener("click", () => openSnapshotForm(null));

    main.querySelectorAll("[data-edit]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        openSnapshotForm(await api.snapshot(btn.dataset.edit));
      }),
    );

    main.querySelectorAll("[data-del]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const s = snapshots.find((x) => String(x.id) === btn.dataset.del);
        confirmDelete(monthLabel(s.month), async () => {
          await api.deleteSnapshot(s.id);
          toast("已刪除");
          rerender();
        });
      }),
    );
  });
}

// ---------------------------------------------------------------------- reminders

const FREQ_LABEL = { once: "單次", monthly: "每月", yearly: "每年" };

function reminderForm(r) {
  const sel = (v) => (r?.frequency === v ? "selected" : "");
  return `<h2>${r ? "編輯" : "新增"}提醒</h2>
    <form>
      <div class="field"><label for="r-title">標題</label>
        <input id="r-title" name="title" required maxlength="200" value="${esc(r?.title || "")}"></div>
      <div class="field"><label for="r-freq">頻率</label>
        <select id="r-freq" name="frequency">
          <option value="monthly" ${sel("monthly")}>每月</option>
          <option value="yearly" ${sel("yearly")}>每年</option>
          <option value="once" ${sel("once")}>單次</option>
        </select></div>
      <div class="field" data-when="monthly yearly"><label for="r-day">日</label>
        <input id="r-day" name="day_of_month" type="number" min="1" max="31"
               value="${esc(r?.day_of_month || 1)}"></div>
      <div class="field" data-when="yearly"><label for="r-month">月</label>
        <input id="r-month" name="month_of_year" type="number" min="1" max="12"
               value="${esc(r?.month_of_year || 1)}"></div>
      <div class="field" data-when="once"><label for="r-date">日期</label>
        <input id="r-date" name="on_date" type="date" value="${esc(r?.on_date || todayISO())}"></div>
      <div class="field"><label for="r-before">提前幾天提醒</label>
        <input id="r-before" name="days_before" type="number" min="0" max="365"
               value="${esc(r?.days_before ?? 0)}"></div>
      <div class="field"><label for="r-note">備註</label>
        <input id="r-note" name="note" maxlength="500" value="${esc(r?.note || "")}"></div>
      <div class="field"><label>
        <input type="checkbox" name="active" ${r?.active !== false ? "checked" : ""}> 啟用</label></div>
      <div class="modal-actions">
        <button type="button" class="btn" data-close>取消</button>
        <button type="submit" class="btn primary">儲存</button>
      </div>
    </form>`;
}

/** Build the payload the API's cross-field rules accept.
 *
 *  ReminderIn rejects a monthly reminder with no day_of_month, and a once reminder with
 *  no on_date. Sending every field regardless would attach a day to a one-off, so the
 *  fields that do not apply are dropped rather than sent as null. */
function reminderPayload(form) {
  const frequency = form.get("frequency");
  const base = {
    title: form.get("title"),
    frequency,
    days_before: Number(form.get("days_before") || 0),
    note: form.get("note") || null,
    active: form.get("active") === "on",
  };
  if (frequency === "once") return { ...base, on_date: form.get("on_date") };
  if (frequency === "monthly") return { ...base, day_of_month: Number(form.get("day_of_month")) };
  return {
    ...base,
    day_of_month: Number(form.get("day_of_month")),
    month_of_year: Number(form.get("month_of_year")),
  };
}

export function reminders(main, rerender) {
  return guard(main, async () => {
    const all = await api.reminders(false);

    main.innerHTML = `
      <h1 class="page-title">提醒</h1>
      <div class="card">
        <div class="card-head-row"><h2>${all.length} 筆</h2>
          <button class="btn" id="add-reminder">新增</button></div>
        ${
          all.length
            ? all
                .map(
                  (r) => `<div class="due-item" ${r.active ? "" : 'style="opacity:.5"'}>
                    <span class="freq-tag">${FREQ_LABEL[r.frequency]}</span>
                    <div style="flex:1">
                      <div>${esc(r.title)}</div>
                      <div class="muted">
                        ${r.next_due ? `下次：${fmtDate(r.next_due)}` : "已過期"}
                        ${r.days_until_due !== null ? `（${r.days_until_due} 天後）` : ""}
                        ${r.days_before ? `· 提前 ${r.days_before} 天` : ""}
                        ${r.active ? "" : "· 已停用"}
                      </div>
                      ${r.note ? `<div class="todo-note muted">${esc(r.note)}</div>` : ""}
                    </div>
                    <div class="row-actions">
                      <button class="btn tiny" data-edit-r="${r.id}">編輯</button>
                      <button class="btn tiny danger" data-del-r="${r.id}">刪除</button>
                    </div>
                  </div>`,
                )
                .join("")
            : '<div class="empty-note">還沒有提醒</div>'
        }
      </div>`;

    const openForm = (r) => {
      const overlay = openModal(reminderForm(r), {
        onSubmit: async (form) => {
          const payload = reminderPayload(form);
          if (r) await api.replaceReminder(r.id, payload);
          else await api.createReminder(payload);
          closeModal();
          toast("已儲存");
          rerender();
        },
      });

      // Only show the fields the chosen frequency actually uses.
      const select = overlay.querySelector('[name="frequency"]');
      const sync = () => {
        overlay.querySelectorAll("[data-when]").forEach((field) => {
          field.hidden = !field.dataset.when.split(" ").includes(select.value);
        });
      };
      select.addEventListener("change", sync);
      sync();
    };

    main.querySelector("#add-reminder").addEventListener("click", () => openForm(null));
    main.querySelectorAll("[data-edit-r]").forEach((b) =>
      b.addEventListener("click", () => openForm(all.find((x) => String(x.id) === b.dataset.editR))),
    );
    main.querySelectorAll("[data-del-r]").forEach((b) =>
      b.addEventListener("click", () => {
        const r = all.find((x) => String(x.id) === b.dataset.delR);
        confirmDelete(r.title, async () => {
          await api.deleteReminder(r.id);
          toast("已刪除");
          rerender();
        });
      }),
    );
  });
}

// -------------------------------------------------------------------------- lists

let currentListId = null;
let search = "";

export function lists(main, rerender) {
  return guard(main, async () => {
    const all = await api.lists();

    if (!all.length) {
      main.innerHTML = `<h1 class="page-title">清單</h1>
        <div class="card"><div class="card-head-row"><h2>清單</h2>
          <button class="btn" id="add-list">新增清單</button></div>
          <div class="empty-note">還沒有清單</div></div>`;
      main.querySelector("#add-list").addEventListener("click", () => openListForm(null, rerender));
      return;
    }

    if (!all.some((l) => l.id === currentListId)) currentListId = all[0].id;
    const active = all.find((l) => l.id === currentListId);

    const q = search.trim().toLowerCase();
    const rows = active.items.filter(
      (row) => !q || row.values.some((v) => String(v).toLowerCase().includes(q)),
    );

    main.innerHTML = `
      <h1 class="page-title">清單</h1>
      <div class="lists-layout">
        <div class="list-nav">
          ${all
            .map(
              (l) => `<button class="list-nav-btn ${l.id === currentListId ? "active" : ""}"
                data-list="${l.id}">
                <span>${esc(l.icon || "📄")}</span><span>${esc(l.name)}</span>
                <span class="cnt">${l.items.length}</span></button>`,
            )
            .join("")}
          <button class="btn tiny" id="add-list">＋ 新增清單</button>
        </div>

        <div class="list-main">
          <div class="list-toolbar">
            <input type="search" id="search" placeholder="搜尋" value="${esc(search)}">
            <button class="btn" id="add-row">新增一列</button>
            <button class="btn tiny" id="edit-list">設定</button>
            <button class="btn tiny danger" id="del-list">刪除清單</button>
          </div>
          <div class="table-wrap">
            <table class="list-table">
              <thead><tr>${active.columns.map((c) => `<th>${esc(c)}</th>`).join("")}<th></th></tr></thead>
              <tbody>
                ${
                  rows.length
                    ? rows
                        .map(
                          (row) => `<tr data-row="${row.id}">
                      ${row.values
                        .map(
                          (v, i) =>
                            `<td><input value="${esc(v)}" data-col="${i}"
                               aria-label="${esc(active.columns[i])}"></td>`,
                        )
                        .join("")}
                      <td><button class="btn tiny danger" data-del-row="${row.id}">×</button></td>
                    </tr>`,
                        )
                        .join("")
                    : `<tr><td colspan="${active.columns.length + 1}" class="empty-note">
                         ${q ? "沒有符合的資料" : "還沒有資料"}</td></tr>`
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>`;

    main.querySelectorAll("[data-list]").forEach((b) =>
      b.addEventListener("click", () => {
        currentListId = Number(b.dataset.list);
        search = "";
        rerender();
      }),
    );

    const searchBox = main.querySelector("#search");
    searchBox.addEventListener("input", () => {
      search = searchBox.value;
      rerender().then(() => {
        // Re-rendering replaces the input, so focus and caret have to be restored or
        // typing a second character would go nowhere.
        const box = document.getElementById("search");
        if (box) {
          box.focus();
          box.setSelectionRange(box.value.length, box.value.length);
        }
      });
    });

    // Save a cell on blur rather than on every keystroke: one request per edit
    // instead of one per character, and no debounce timer to reason about.
    main.querySelectorAll("[data-row] input").forEach((input) => {
      const original = input.value;
      input.addEventListener("blur", async () => {
        if (input.value === original) return;
        const tr = input.closest("tr");
        const values = [...tr.querySelectorAll("input")].map((i) => i.value);
        try {
          await api.replaceRow(active.id, Number(tr.dataset.row), values);
          toast("已儲存");
        } catch (err) {
          input.value = original;
          toast(err.detail || "儲存失敗");
        }
      });
    });

    main.querySelectorAll("[data-del-row]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api.deleteRow(active.id, Number(b.dataset.delRow));
        toast("已刪除");
        rerender();
      }),
    );

    main.querySelector("#add-row").addEventListener("click", async () => {
      await api.createRow(active.id, active.columns.map(() => ""));
      rerender();
    });

    main.querySelector("#add-list").addEventListener("click", () => openListForm(null, rerender));
    main.querySelector("#edit-list").addEventListener("click", () => openListForm(active, rerender));
    main.querySelector("#del-list").addEventListener("click", () =>
      confirmDelete(active.name, async () => {
        await api.deleteList(active.id);
        currentListId = null;
        toast("已刪除");
        rerender();
      }),
    );
  });
}

function openListForm(list, rerender) {
  openModal(
    `<h2>${list ? "清單設定" : "新增清單"}</h2>
     <form>
       <div class="field"><label for="l-name">名稱</label>
         <input id="l-name" name="name" required maxlength="120" value="${esc(list?.name || "")}"></div>
       <div class="field"><label for="l-icon">圖示</label>
         <input id="l-icon" name="icon" maxlength="16" value="${esc(list?.icon || "📄")}"></div>
       <div class="field"><label for="l-cols">欄位（用逗號分隔）</label>
         <input id="l-cols" name="columns" required
                value="${esc((list?.columns || ["項目", "備註"]).join(", "))}">
         ${
           list?.items?.length
             ? `<div class="muted" style="font-size:12px;margin-top:4px">
                  這個清單已有 ${list.items.length} 列資料，只能改欄位名稱、不能增減欄位數量</div>`
             : ""
         }
       </div>
       <div class="modal-actions">
         <button type="button" class="btn" data-close>取消</button>
         <button type="submit" class="btn primary">儲存</button>
       </div>
     </form>`,
    {
      onSubmit: async (form) => {
        const payload = {
          name: form.get("name"),
          icon: form.get("icon") || null,
          columns: form
            .get("columns")
            .split(",")
            .map((c) => c.trim())
            .filter(Boolean),
          position: list?.position ?? 999,
        };
        try {
          if (list) await api.replaceList(list.id, payload);
          else await api.createList(payload);
        } catch (err) {
          toast(err.detail || "儲存失敗");
          return;
        }
        closeModal();
        toast("已儲存");
        rerender();
      },
    },
  );
}
