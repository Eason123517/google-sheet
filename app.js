const DEFAULT_API_BASE_URL = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec";
const API_STORAGE_KEY = "stockTrackerApiBaseUrl";

const state = {
  stocks: [],
  transactions: [],
  portfolio: [],
  dashboard: null,
  analysis: null,
  distribution: [],
};

const el = {
  apiForm: document.querySelector("#api-form"),
  apiUrl: document.querySelector("#api-url"),
  apiStatus: document.querySelector("#api-status"),
  tradeForm: document.querySelector("#trade-form"),
  stockForm: document.querySelector("#stock-form"),
  historyFilter: document.querySelector("#history-filter"),
  stocksBody: document.querySelector("#stocks-body"),
  portfolioBody: document.querySelector("#portfolio-body"),
  historyBody: document.querySelector("#history-body"),
  refreshPortfolio: document.querySelector("#refresh-portfolio"),
  tabs: document.querySelectorAll(".tab-btn"),
  panels: document.querySelectorAll(".tab-panel"),
  kpiInvested: document.querySelector("#kpi-invested"),
  kpiMarket: document.querySelector("#kpi-market"),
  kpiProfit: document.querySelector("#kpi-profit"),
  kpiReturn: document.querySelector("#kpi-return"),
  anaWin: document.querySelector("#ana-winrate"),
  anaAvg: document.querySelector("#ana-avg"),
  anaDd: document.querySelector("#ana-dd"),
  anaCount: document.querySelector("#ana-count"),
  chart: document.querySelector("#distribution-chart"),
};

const formatNumber = (v) => Number(v || 0).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
const formatMoney = (v) => {
  const n = Number(v || 0);
  const sign = n < 0 ? "-" : "";
  return `${sign}NTD$${Math.abs(n).toLocaleString("zh-TW", { maximumFractionDigits: 2 })}`;
};
const formatPct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;

function getApiBaseUrl() {
  return (localStorage.getItem(API_STORAGE_KEY) || DEFAULT_API_BASE_URL).trim();
}

function setApiStatus(message, type = "") {
  el.apiStatus.textContent = message;
  el.apiStatus.className = `api-status ${type}`.trim();
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

  const data = await response.json();
  if (data && data.error) throw new Error(data.error);
  return data;
}

async function submitJson(path, payload) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=utf-8" },
    body: JSON.stringify(payload),
  });
}

function calcTxAmount() {
  const type = el.tradeForm.querySelector("#tx-type").value;
  const price = Number(el.tradeForm.querySelector("#tx-price").value || 0);
  const qty = Number(el.tradeForm.querySelector("#tx-qty").value || 0);
  const fee = Number(el.tradeForm.querySelector("#tx-fee").value || 0);

  let amount = price * qty;
  if (type === "SELL") amount = -amount;
  if (type === "BUY") amount += fee;
  if (type === "SELL") amount += fee;
  if (type === "CASH_DIV") amount = -(price * qty);
  if (type === "STOCK_DIV") amount = 0;

  el.tradeForm.querySelector("#tx-amount").value = amount.toFixed(2);
}

function findStockBySymbol(symbol) {
  return state.stocks.find((s) => s.symbol === symbol.toUpperCase());
}

function renderStocks() {
  el.stocksBody.innerHTML = "";
  state.stocks.forEach((s) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${s.symbol}</td><td>${s.name || "-"}</td><td>${s.market || "-"}</td><td>${s.industry || "-"}</td>`;
    el.stocksBody.appendChild(tr);
  });
}

function renderPortfolio() {
  el.portfolioBody.innerHTML = "";
  state.portfolio.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.symbol} ${p.name || ""}</td>
      <td>${formatNumber(p.shares)}</td>
      <td>${formatMoney(p.avgCost)}</td>
      <td>${formatMoney(p.marketPrice)}</td>
      <td>${formatMoney(p.cost)}</td>
      <td>${formatMoney(p.marketValue)}</td>
      <td class="${p.profit >= 0 ? "profit" : "loss"}">${formatMoney(p.profit)}</td>
      <td class="${p.returnRate >= 0 ? "profit" : "loss"}">${formatPct(p.returnRate)}</td>
    `;
    el.portfolioBody.appendChild(tr);
  });
}

function renderDashboard() {
  const d = state.dashboard || { totalInvested: 0, totalMarketValue: 0, totalProfit: 0, totalReturnRate: 0 };
  el.kpiInvested.textContent = formatMoney(d.totalInvested);
  el.kpiMarket.textContent = formatMoney(d.totalMarketValue);
  el.kpiProfit.textContent = formatMoney(d.totalProfit);
  el.kpiProfit.className = d.totalProfit >= 0 ? "profit" : "loss";
  el.kpiReturn.textContent = formatPct(d.totalReturnRate);
  el.kpiReturn.className = d.totalReturnRate >= 0 ? "profit" : "loss";
}

function renderAnalysis() {
  const a = state.analysis || { winRate: 0, avgReturn: 0, maxDrawdown: 0, tradeCount: 0 };
  el.anaWin.textContent = formatPct(a.winRate);
  el.anaAvg.textContent = formatPct(a.avgReturn);
  el.anaDd.textContent = formatPct(a.maxDrawdown);
  el.anaCount.textContent = String(a.tradeCount || 0);
}

function renderHistory(rows) {
  el.historyBody.innerHTML = "";
  rows.forEach((t) => {
    const tr = document.createElement("tr");
    const typeLabel = { BUY: "買入", SELL: "賣出", CASH_DIV: "現金股利", STOCK_DIV: "股票股利" }[t.type] || t.type;
    tr.innerHTML = `
      <td>${t.date}</td><td>${t.symbol}</td><td>${t.name || "-"}</td><td>${typeLabel}</td>
      <td>${formatMoney(t.price)}</td><td>${formatNumber(t.qty)}</td><td>${formatMoney(t.fee)}</td>
      <td>${formatMoney(t.amount)}</td><td>${t.note || ""}</td>
    `;
    el.historyBody.appendChild(tr);
  });
}

function renderDistribution() {
  const canvas = el.chart;
  const ctx = canvas.getContext("2d");
  const list = state.distribution || [];

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!list.length) {
    ctx.fillStyle = "#64748b";
    ctx.font = "16px sans-serif";
    ctx.fillText("尚無資料可繪製", 20, 30);
    return;
  }

  const total = list.reduce((sum, i) => sum + i.value, 0);
  let start = -Math.PI / 2;
  const colors = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#0891b2", "#ca8a04"];

  list.forEach((item, idx) => {
    const slice = (item.value / total) * Math.PI * 2;
    const end = start + slice;

    ctx.beginPath();
    ctx.moveTo(180, 160);
    ctx.arc(180, 160, 110, start, end);
    ctx.closePath();
    ctx.fillStyle = colors[idx % colors.length];
    ctx.fill();

    const percent = ((item.value / total) * 100).toFixed(1);
    const y = 26 + idx * 24;
    ctx.fillStyle = colors[idx % colors.length];
    ctx.fillRect(360, y - 10, 12, 12);
    ctx.fillStyle = "#334155";
    ctx.font = "14px sans-serif";
    ctx.fillText(`${item.name}：${percent}% (${formatMoney(item.value)})`, 378, y);

    start = end;
  });
}

async function loadStocks() {
  state.stocks = await api("stocks");
  renderStocks();
}

async function loadPortfolio() {
  state.portfolio = await api("portfolio");
  renderPortfolio();
}

async function loadDashboard() {
  state.dashboard = await api("dashboard");
  renderDashboard();
}

async function loadAnalysis() {
  state.analysis = await api("analysis");
  renderAnalysis();
}

async function loadDistribution() {
  state.distribution = await api("distribution");
  renderDistribution();
}

async function loadHistory(filters = {}) {
  const query = new URLSearchParams({ path: "transactions", ...filters });
  const baseUrl = getApiBaseUrl();
  validateApiBaseUrl(baseUrl);
  const response = await fetch(`${baseUrl}?${query.toString()}`);
  const data = await response.json();
  state.transactions = data;
  renderHistory(state.transactions);
}

async function loadAll() {
  await Promise.all([
    loadStocks(),
    loadPortfolio(),
    loadDashboard(),
    loadAnalysis(),
    loadDistribution(),
    loadHistory(),
  ]);
  setApiStatus("連線成功", "success");
}

el.tradeForm.addEventListener("input", (e) => {
  if (["tx-symbol", "tx-type", "tx-price", "tx-qty", "tx-fee"].includes(e.target.id)) {
    if (e.target.id === "tx-symbol") {
      const stock = findStockBySymbol(e.target.value.trim());
      if (stock) el.tradeForm.querySelector("#tx-name").value = stock.name || "";
    }
    calcTxAmount();
  }
});

el.tradeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    date: el.tradeForm.querySelector("#tx-date").value,
    symbol: el.tradeForm.querySelector("#tx-symbol").value.trim().toUpperCase(),
    name: el.tradeForm.querySelector("#tx-name").value.trim(),
    type: el.tradeForm.querySelector("#tx-type").value,
    price: Number(el.tradeForm.querySelector("#tx-price").value),
    qty: Number(el.tradeForm.querySelector("#tx-qty").value),
    fee: Number(el.tradeForm.querySelector("#tx-fee").value || 0),
    note: el.tradeForm.querySelector("#tx-note").value.trim(),
  };
  try {
    await submitJson("transactions", payload);
    await loadAll();
    el.tradeForm.reset();
    initTradeDefaults();
  } catch (err) {
    setApiStatus(err.message, "error");
  }
});

el.stockForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await submitJson("stocks", {
      symbol: document.querySelector("#stock-symbol").value.trim().toUpperCase(),
      name: document.querySelector("#stock-name").value.trim(),
      market: document.querySelector("#stock-market").value.trim(),
      industry: document.querySelector("#stock-industry").value.trim(),
    });
    el.stockForm.reset();
    await loadStocks();
  } catch (err) {
    setApiStatus(err.message, "error");
  }
});

el.historyFilter.addEventListener("submit", async (e) => {
  e.preventDefault();
  const filters = {
    symbol: document.querySelector("#filter-symbol").value.trim().toUpperCase(),
    type: document.querySelector("#filter-type").value,
    startDate: document.querySelector("#filter-start").value,
    endDate: document.querySelector("#filter-end").value,
  };
  try {
    await loadHistory(filters);
  } catch (err) {
    setApiStatus(err.message, "error");
  }
});

el.refreshPortfolio.addEventListener("click", async () => {
  try {
    await submitJson("refresh", {});
    await Promise.all([loadPortfolio(), loadDashboard(), loadDistribution()]);
  } catch (err) {
    setApiStatus(err.message, "error");
  }
});

el.apiForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  localStorage.setItem(API_STORAGE_KEY, el.apiUrl.value.trim());
  try {
    await loadAll();
  } catch (err) {
    setApiStatus(err.message, "error");
  }
});

el.tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    el.tabs.forEach((b) => b.classList.remove("active"));
    el.panels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.querySelector(`#tab-${btn.dataset.tab}`).classList.add("active");
  });
});

function initTradeDefaults() {
  document.querySelector("#tx-date").value = new Date().toISOString().slice(0, 10);
  document.querySelector("#tx-type").value = "BUY";
  document.querySelector("#tx-fee").value = 0;
  calcTxAmount();
}

el.apiUrl.value = getApiBaseUrl();
initTradeDefaults();
loadAll().catch((err) => setApiStatus(err.message, "error"));
setInterval(() => {
  Promise.all([loadPortfolio(), loadDashboard(), loadDistribution()]).catch(() => {});
}, 5 * 60 * 1000);
