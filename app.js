const DEFAULT_API_BASE_URL = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec";
const API_STORAGE_KEY = "stockTrackerApiBaseUrl";

const state = {
  positions: [],
  trades: [],
};

const positionForm = document.querySelector("#position-form");
const tradeForm = document.querySelector("#trade-form");
const positionsBody = document.querySelector("#positions-body");
const tradesBody = document.querySelector("#trades-body");
const summaryEl = document.querySelector("#summary");
const refreshBtn = document.querySelector("#refresh");
const resetFormBtn = document.querySelector("#reset-form");
const apiForm = document.querySelector("#api-form");
const apiUrlInput = document.querySelector("#api-url");
const apiStatus = document.querySelector("#api-status");

const formatNumber = (v) => Number(v || 0).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
const formatMoney = (v) =>
  Number(v || 0).toLocaleString("zh-TW", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });

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
  const apiBaseUrl = getApiBaseUrl();
  validateApiBaseUrl(apiBaseUrl);

  const response = await fetch(`${apiBaseUrl}?path=${encodeURIComponent(path)}`, {
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

function fillPositionForm(row) {
  positionForm.symbol.value = row.symbol;
  positionForm.name.value = row.name || "";
  positionForm.shares.value = row.shares;
  positionForm.avgCost.value = row.avgCost;
}

function renderPositions() {
  positionsBody.innerHTML = "";

  let totalPnl = 0;

  state.positions.forEach((row) => {
    const marketValue = Number(row.currentPrice) * Number(row.shares);
    const costValue = Number(row.avgCost) * Number(row.shares);
    const pnl = marketValue - costValue;
    totalPnl += pnl;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.symbol}</td>
      <td>${row.name || "-"}</td>
      <td>${formatNumber(row.shares)}</td>
      <td>${formatMoney(row.avgCost)}</td>
      <td>${formatMoney(row.currentPrice)}</td>
      <td>${formatMoney(marketValue)}</td>
      <td class="${pnl >= 0 ? "profit" : "loss"}">${formatMoney(pnl)}</td>
      <td>
        <button data-action="edit" data-symbol="${row.symbol}" class="secondary">編輯</button>
        <button data-action="delete" data-symbol="${row.symbol}" class="danger">刪除</button>
      </td>
    `;

    positionsBody.appendChild(tr);
  });

  summaryEl.className = `summary ${totalPnl >= 0 ? "profit" : "loss"}`;
  summaryEl.textContent = `總損益：${formatMoney(totalPnl)}`;
}

function renderTrades() {
  tradesBody.innerHTML = "";

  state.trades.forEach((trade) => {
    const cost = Number(trade.shares) * Number(trade.price);
    const currentValue = Number(trade.shares) * Number(trade.currentPrice);
    const pnl = currentValue - cost;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date(trade.buyTime).toLocaleString("zh-TW")}</td>
      <td>${trade.symbol}</td>
      <td>${formatNumber(trade.shares)}</td>
      <td>${formatMoney(trade.price)}</td>
      <td>${formatMoney(cost)}</td>
      <td>${formatMoney(currentValue)}</td>
      <td class="${pnl >= 0 ? "profit" : "loss"}">${formatMoney(pnl)}</td>
    `;
    tradesBody.appendChild(tr);
  });
}

async function loadData() {
  const [positions, trades] = await Promise.all([api("positions"), api("trades")]);
  state.positions = positions;
  state.trades = trades;
  renderPositions();
  renderTrades();
  setApiStatus("連線成功", "success");
}

async function submitJson(path, payload) {
  // Apps Script Web App 在某些環境下對 application/json 會觸發 preflight；
  // 這裡改用 text/plain 避免 CORS 預檢失敗。
  return api(path, {
    method: "POST",
    headers: {
      "Content-Type": "text/plain;charset=utf-8",
    },
    body: JSON.stringify(payload),
  });
}

positionForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    symbol: positionForm.symbol.value.trim().toUpperCase(),
    name: positionForm.name.value.trim(),
    shares: Number(positionForm.shares.value),
    avgCost: Number(positionForm.avgCost.value),
  };

  try {
    await submitJson("positions", payload);
    positionForm.reset();
    await loadData();
  } catch (error) {
    setApiStatus(error.message, "error");
    alert(error.message);
  }
});

tradeForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  try {
    await submitJson("trades", {
      symbol: tradeForm.tradeSymbol.value.trim().toUpperCase(),
      shares: Number(tradeForm.tradeShares.value),
      price: Number(tradeForm.tradePrice.value),
      buyTime: new Date(tradeForm.tradeTime.value).toISOString(),
    });

    tradeForm.reset();
    await loadData();
  } catch (error) {
    setApiStatus(error.message, "error");
    alert(error.message);
  }
});

positionsBody.addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;

  const symbol = button.dataset.symbol;
  const row = state.positions.find((item) => item.symbol === symbol);

  if (button.dataset.action === "edit" && row) {
    fillPositionForm(row);
    return;
  }

  if (button.dataset.action === "delete") {
    try {
      await submitJson("positions/delete", { symbol });
      await loadData();
    } catch (error) {
      setApiStatus(error.message, "error");
      alert(error.message);
    }
  }
});

apiForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const value = apiUrlInput.value.trim();
  localStorage.setItem(API_STORAGE_KEY, value);
  try {
    await loadData();
  } catch (error) {
    setApiStatus(error.message, "error");
  }
});

resetFormBtn.addEventListener("click", () => positionForm.reset());
refreshBtn.addEventListener("click", () => {
  loadData().catch((error) => setApiStatus(error.message, "error"));
});

apiUrlInput.value = getApiBaseUrl();
loadData().catch((error) => {
  setApiStatus(error.message, "error");
});
