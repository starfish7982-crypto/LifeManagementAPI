/** Shell: sign-in gate, navigation, and dispatch to the views. */

import { api, session, setUnauthorisedHandler } from "./api.js";
import * as views from "./views.js";
import { closeModal, openModal, toast } from "./ui.js";

const authScreen = document.getElementById("auth");
const appShell = document.getElementById("app");
const main = document.getElementById("main");

const VIEWS = {
  today: views.today,
  dashboard: views.dashboard,
  assets: views.assets,
  lists: views.lists,
  reminders: views.reminders,
};

let currentView = "today";

function render() {
  const view = VIEWS[currentView] || VIEWS.today;
  // Views take `render` so they can refresh after a write. Refetching rather than
  // patching local state means the screen always shows what the server actually
  // stored — including the id and any normalisation it applied on the way in.
  return view(main, render);
}

// ------------------------------------------------------------------ sign-in gate

function showAuth(message) {
  appShell.hidden = true;
  authScreen.hidden = false;
  if (message) showAuthError(message);
}

function showApp() {
  authScreen.hidden = true;
  appShell.hidden = false;
  document.getElementById("signed-in-as").textContent = session.email || "";
  return render();
}

setUnauthorisedHandler(() => showAuth("登入已過期，請重新登入"));

const form = document.getElementById("auth-form");
const errorBox = document.getElementById("auth-error");
const submit = document.getElementById("auth-submit");
const toggle = document.getElementById("auth-toggle");
const toggleText = document.getElementById("auth-toggle-text");
const subtitle = document.getElementById("auth-sub");

let mode = "login";

function showAuthError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

toggle.addEventListener("click", () => {
  mode = mode === "login" ? "register" : "login";
  errorBox.hidden = true;
  const registering = mode === "register";
  submit.textContent = registering ? "註冊" : "登入";
  toggle.textContent = registering ? "登入" : "註冊";
  toggleText.textContent = registering ? "已經有帳號了？" : "還沒有帳號？";
  subtitle.textContent = registering ? "建立新帳號" : "登入以檢視你的資料";
  document.getElementById("auth-password").autocomplete = registering
    ? "new-password"
    : "current-password";
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.hidden = true;

  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;

  submit.disabled = true;
  submit.textContent = "請稍候…（首次連線需要喚醒服務）";
  try {
    if (mode === "register") {
      await api.register(email, password);
      toast("帳號已建立");
    }
    await api.login(email, password);
    await showApp();
  } catch (err) {
    // 401 here is a rejected credential, not an expired session, so it must not go
    // through the global handler — that would clear a token the user never had.
    showAuthError(
      err.status === 401
        ? "Email 或密碼不正確。若還沒有帳號，請先註冊。"
        : err.detail || "登入失敗",
    );
  } finally {
    submit.disabled = false;
    submit.textContent = mode === "register" ? "註冊" : "登入";
  }
});

// -------------------------------------------------------------------- navigation

document.querySelectorAll(".nav-btn").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentView = btn.dataset.view;
    render();
  }),
);

document.getElementById("sign-out").addEventListener("click", () => {
  session.clear();
  showAuth();
});

document.getElementById("change-password").addEventListener("click", () => {
  openModal(
    `<h2>變更密碼</h2>
     <form method="post" action="">
       <div class="field"><label for="pw-current">目前密碼</label>
         <input id="pw-current" name="current" type="password"
                autocomplete="current-password" required></div>
       <div class="field"><label for="pw-new">新密碼（至少 8 個字）</label>
         <input id="pw-new" name="next" type="password"
                autocomplete="new-password" minlength="8" required></div>
       <p class="auth-error" id="pw-error" hidden></p>
       <div class="modal-actions">
         <button type="button" class="btn" data-close>取消</button>
         <button type="submit" class="btn primary">變更</button>
       </div>
     </form>`,
    {
      onSubmit: async (form) => {
        const box = document.getElementById("pw-error");
        box.hidden = true;
        try {
          await api.changePassword(form.get("current"), form.get("next"));
        } catch (err) {
          box.textContent =
            err.status === 401 ? "目前密碼不正確" : err.detail || "變更失敗";
          box.hidden = false;
          return;
        }
        closeModal();
        toast("密碼已變更");
      },
    },
  );
});

// ------------------------------------------------------------------------- start

async function start() {
  if (!session.token) {
    showAuth();
    return;
  }
  // A stored token may be expired. Verifying it once here means the first thing the
  // user sees is either their data or the sign-in form — never a view that renders
  // and then collapses into an error.
  try {
    await api.me();
    await showApp();
  } catch {
    showAuth();
  }
}

start();
