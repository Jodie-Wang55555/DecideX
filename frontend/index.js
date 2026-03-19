const API_BASE_URL = "http://localhost:8123";
const AUTH_TOKEN_KEY = "decidex_auth_token";
const AUTH_EMAIL_KEY = "decidex_auth_email";

// 从 localStorage 直接读取，不发请求
const modalState = {
  token: localStorage.getItem(AUTH_TOKEN_KEY) || "",
  email: localStorage.getItem(AUTH_EMAIL_KEY) || "",
};

// ── Tab 切换：登录 / 注册 ────────────────────────────────────
function switchAuthTab(tab) {
  const btnLogin    = document.getElementById("tab-login");
  const btnRegister = document.getElementById("tab-register");
  const submitBtn   = document.getElementById("auth-submit-btn");
  const passInput   = document.getElementById("modal-auth-password");
  const hint        = document.getElementById("modal-auth-hint");
  if (hint) hint.textContent = "";
  if (tab === "login") {
    btnLogin?.classList.add("active");
    btnRegister?.classList.remove("active");
    if (submitBtn) { submitBtn.textContent = "登录"; submitBtn.onclick = modalLogin; }
    if (passInput) passInput.placeholder = "请输入密码";
  } else {
    btnRegister?.classList.add("active");
    btnLogin?.classList.remove("active");
    if (submitBtn) { submitBtn.textContent = "注册账号"; submitBtn.onclick = modalRegister; }
    if (passInput) passInput.placeholder = "设置密码（6位以上）";
  }
}

// ── 更新弹窗 UI（纯 DOM，无请求）────────────────────────────
function _updateModalAuthUI() {
  const guestEl  = document.getElementById("modal-auth-guest");
  const loginEl  = document.getElementById("modal-auth-loggedin");
  const emailEl  = document.getElementById("modal-loggedin-email");
  const avatarEl = document.getElementById("modal-user-avatar");
  if (modalState.token && modalState.email) {
    if (guestEl)  guestEl.style.display = "none";
    if (loginEl)  loginEl.style.display = "block";
    if (emailEl)  emailEl.textContent   = modalState.email;
    if (avatarEl) avatarEl.textContent  = modalState.email[0].toUpperCase();
  } else {
    if (guestEl)  guestEl.style.display = "block";
    if (loginEl)  loginEl.style.display = "none";
  }
}

// ── 登录（1 个请求）─────────────────────────────────────────
async function modalLogin() {
  const emailVal = (document.getElementById("modal-auth-email")?.value || "").trim().toLowerCase();
  const passVal  = (document.getElementById("modal-auth-password")?.value || "").trim();
  const hint     = document.getElementById("modal-auth-hint");
  const btn      = document.getElementById("auth-submit-btn");
  if (!emailVal || !passVal) { if (hint) hint.textContent = "请填写邮箱和密码。"; return; }

  if (btn) { btn.textContent = "登录中..."; btn.disabled = true; }
  try {
    const res  = await fetch(`${API_BASE_URL}/auth/login`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email: emailVal, password: passVal })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "邮箱或密码错误");

    // 保存到 localStorage + 内存
    modalState.token = data.token;
    modalState.email = data.email;
    localStorage.setItem(AUTH_TOKEN_KEY, data.token);
    localStorage.setItem(AUTH_EMAIL_KEY, data.email);

    // 把邮箱写入 profile（profile 的其他字段由决策页槽位系统收集）
    const profile = JSON.parse(localStorage.getItem("decidex_user_profile") || "{}");
    profile.email = data.email;
    localStorage.setItem("decidex_user_profile", JSON.stringify(profile));

    _updateModalAuthUI();
  } catch (e) {
    if (hint) hint.textContent = e.message;
    if (btn)  { btn.textContent = "登录"; btn.disabled = false; }
  }
}

// ── 注册（1 个请求）─────────────────────────────────────────
async function modalRegister() {
  const emailVal = (document.getElementById("modal-auth-email")?.value || "").trim().toLowerCase();
  const passVal  = (document.getElementById("modal-auth-password")?.value || "").trim();
  const hint     = document.getElementById("modal-auth-hint");
  const btn      = document.getElementById("auth-submit-btn");
  if (!emailVal || !passVal) { if (hint) hint.textContent = "请填写邮箱和密码。"; return; }
  if (passVal.length < 6)    { if (hint) hint.textContent = "密码至少 6 位。"; return; }

  if (btn) { btn.textContent = "注册中..."; btn.disabled = true; }
  try {
    const res  = await fetch(`${API_BASE_URL}/auth/register`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email: emailVal, password: passVal })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "注册失败，邮箱可能已存在");

    modalState.token = data.token;
    modalState.email = data.email;
    localStorage.setItem(AUTH_TOKEN_KEY, data.token);
    localStorage.setItem(AUTH_EMAIL_KEY, data.email);

    const profile = JSON.parse(localStorage.getItem("decidex_user_profile") || "{}");
    profile.email = data.email;
    localStorage.setItem("decidex_user_profile", JSON.stringify(profile));

    _updateModalAuthUI();
    if (hint) hint.textContent = "注册成功 🎉";
  } catch (e) {
    if (hint) hint.textContent = e.message;
    if (btn)  { btn.textContent = "注册账号"; btn.disabled = false; }
  }
}

// ── 退出（fire-and-forget，不阻塞 UI）──────────────────────
function modalLogout() {
  // 先立刻清除本地状态，UI 立即响应
  const token = modalState.token;
  modalState.token = ""; modalState.email = "";
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_EMAIL_KEY);
  const e = document.getElementById("modal-auth-email");
  const p = document.getElementById("modal-auth-password");
  if (e) e.value = ""; if (p) p.value = "";
  _updateModalAuthUI();
  // 后台通知服务端（不等结果）
  if (token) fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}` }
  }).catch(() => {});
}

// ── 弹窗开/关（纯 DOM，无请求）──────────────────────────────
function openProfileModal() {
  const overlay = document.getElementById("profile-modal-overlay");
  if (!overlay) { window.location.href = "decision.html"; return; }
  // 同步 localStorage → modalState（无需发请求）
  modalState.token = localStorage.getItem(AUTH_TOKEN_KEY) || "";
  modalState.email = localStorage.getItem(AUTH_EMAIL_KEY) || "";
  _updateModalAuthUI();
  overlay.classList.add("active");
}

function closeProfileModal(event) {
  const overlay = document.getElementById("profile-modal-overlay");
  if (event.target === overlay) overlay.classList.remove("active");
}

function skipProfileAndGo() {
  document.getElementById("profile-modal-overlay")?.classList.remove("active");
  window.location.href = "decision.html";
}

function saveProfileAndGo() {
  const existing = JSON.parse(localStorage.getItem("decidex_user_profile") || "{}");
  if (modalState.email) existing.email = modalState.email;
  localStorage.setItem("decidex_user_profile", JSON.stringify(existing));
  window.location.href = "decision.html";
}

// ── 页面初始化：0 个请求 ──────────────────────────────────────
// token 校验放到决策页真正发请求时再做，首页不发任何请求
