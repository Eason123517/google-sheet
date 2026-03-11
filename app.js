const DEFAULT_API_BASE_URL = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec";
const API_STORAGE_KEY = "stockTrackerApiBaseUrl";

const state = {
  trades: [],
  dashboard: [],
};

const apiForm = document.querySelector("#api-form");
const apiUrlInput = document.querySelector("#api-url");
const apiStatus = document.querySelector("#api-status");
const tradeForm = document.querySelector("#trade-form");
const tradesBody = document.querySelector("#trades-body");
const dashboardBody = document.querySelector("#dashboard-body");
const summaryEl = document.querySelector("#summary");
const refreshTradesBtn = document.querySelector("#refresh-trades");
const refreshDashboardBtn = document.querySelector("#refresh-dashboard");
const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

const formatNumber = (v) => Number(v || 0).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
const formatMoney = (v) => {
  const n = Number(v || 0);
  const sign = n < 0 ? "-" : "";
  return `${sign}NTD$${Math.abs(n).toLocaleString("zh-TW", { maximumFractionDigits: 2 })}`;
};

function getApiBaseUrl() {
  const saved = localStorage.getItem(API_STORAGE_KEY);
  return (saved || DEFAULT_API_BASE_URL).trim();
}

function setApiStatus(message, type = "") {
  apiStatus.textContent = message;
  apiStatus.className = `api-status ${type}`.trim();
}

function validateApiBaseUrl(url) {
  if (!url || url.includes("YOUR_DEPLOYMENT_ID")) {
    throw new Error("請先設定正確的 Apps Script Web App URL。");
  }
}

async function api(path, options = {}) {
  const baseUrl = getApiBaseUrl();
  validateApiBaseUrl(baseUrl);

  const response = await fetch(`${baseUrl}?path=${encodeURIComponent(path)}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(`API 錯誤：${response.status}`);
  }

  return response.json();
}

async function submitJson(path, payload) {
  return api(path, {
    method: "POST",
    headers: {
      "Content-Type": "text/plain;charset=utf-8",
    },
    body: JSON.stringify(payload),
  });
}

function calculateTradeTotal() {
  const action = tradeForm.tradeAction.value;
  const price = Number(tradeForm.tradePrice.value || 0);
  const shares = Number(tradeForm.tradeShares.value || 0);
  const fee = Number(tradeForm.tradeFee.value || 0);
  const gross = price * shares;
  const total = action === "BUY" ? gross + fee : gross - fee;
  tradeForm.tradeTotal.value = Number(total.toFixed(2));
}

function renderTrades() {
  tradesBody.innerHTML = "";

  state.trades.forEach((trade) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${trade.date}</td>
      <td>${trade.symbol}</td>
      <td>${trade.action === "BUY" ? "買" : "賣"}</td>
      <td>${formatMoney(trade.price)}</td>
      <td>${formatNumber(trade.shares)}</td>
      <td>${formatMoney(trade.fee)}</td>
      <td>${formatMoney(trade.total)}</td>
    `;
    tradesBody.appendChild(tr);
  });
}

function renderDashboard() {
  dashboardBody.innerHTML = "";
  let totalUnrealizedPnl = 0;

  state.dashboard.forEach((item) => {
    totalUnrealizedPnl += Number(item.unrealizedPnl || 0);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.symbol}</td>
      <td>${formatNumber(item.shares)}</td>
      <td>${formatMoney(item.avgCost)}</td>
      <td>${formatMoney(item.currentPrice)}</td>
      <td class="${item.unrealizedPnl >= 0 ? "profit" : "loss"}">${formatMoney(item.unrealizedPnl)}</td>
    `;
    dashboardBody.appendChild(tr);
  });

  summaryEl.className = `summary ${totalUnrealizedPnl >= 0 ? "profit" : "loss"}`;
  summaryEl.textContent = `總未實現損益：${formatMoney(totalUnrealizedPnl)}`;
}

async function loadTrades() {
  state.trades = await api("trades");
  renderTrades();
}

async function loadDashboard() {
  state.dashboard = await api("dashboard");
  renderDashboard();
}

async function loadAll() {
  await Promise.all([loadTrades(), loadDashboard()]);
  setApiStatus("連線成功", "success");
}

tradeForm.addEventListener("input", (e) => {
  if (["tradeAction", "tradePrice", "tradeShares", "tradeFee"].includes(e.target.id)) {
    calculateTradeTotal();
  }
});

tradeForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    date: tradeForm.tradeDate.value,
    symbol: tradeForm.tradeSymbol.value.trim().toUpperCase(),
    action: tradeForm.tradeAction.value,
    price: Number(tradeForm.tradePrice.value),
    shares: Number(tradeForm.tradeShares.value),
    fee: Number(tradeForm.tradeFee.value),
    total: Number(tradeForm.tradeTotal.value),
  };

  try {
    await submitJson("trades", payload);
    tradeForm.reset();
    tradeForm.tradeDate.value = new Date().toISOString().slice(0, 10);
    tradeForm.tradeAction.value = "BUY";
    tradeForm.tradeFee.value = 0;
    calculateTradeTotal();
    await loadAll();
  } catch (error) {
    setApiStatus(error.message, "error");
    alert(error.message);
  }
});

refreshTradesBtn.addEventListener("click", () => {
  loadTrades().catch((error) => setApiStatus(error.message, "error"));
});

refreshDashboardBtn.addEventListener("click", () => {
  loadDashboard().catch((error) => setApiStatus(error.message, "error"));
});

apiForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  localStorage.setItem(API_STORAGE_KEY, apiUrlInput.value.trim());
  try {
    await loadAll();
  } catch (error) {
    setApiStatus(error.message, "error");
  }
});

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => b.classList.remove("active"));
    tabPanels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.querySelector(`#tab-${btn.dataset.tab}`).classList.add("active");
  });
});

apiUrlInput.value = getApiBaseUrl();
tradeForm.tradeDate.value = new Date().toISOString().slice(0, 10);
tradeForm.tradeAction.value = "BUY";
tradeForm.tradeFee.value = 0;
calculateTradeTotal();

loadAll().catch((error) => setApiStatus(error.message, "error"));
