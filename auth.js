const API_BASE = "https://diet-analysis-func-bose29445.azurewebsites.net/api";

function saveSession(token, name) {
  localStorage.setItem("token", token);
  localStorage.setItem("name", name);
}

async function requireAuth() {
  if (window.location.hash.startsWith("#token=")) {
    localStorage.setItem("token", window.location.hash.replace("#token=", ""));
    history.replaceState(null, "", window.location.pathname);
  }
  const t = localStorage.getItem("token");
  if (!t) { window.location.href = "login.html"; return null; }

  const res = await fetch(API_BASE + "/auth/me", { headers: { Authorization: "Bearer " + t } });
  if (!res.ok) { localStorage.clear(); window.location.href = "login.html"; return null; }
  return res.json();
}

function logout() { localStorage.clear(); window.location.href = "login.html"; }
