const SHEET_NAMES = {
  transactions: 'transactions',
  stocks: 'stocks',
  portfolio: 'portfolio',
  dashboard: 'dashboard',
};

function doGet(e) {
  const path = getPath(e);
  const q = (e && e.parameter) || {};

  try {
    if (path === 'transactions') {
      return jsonResponse(getTransactions(q));
    }
    if (path === 'stocks') {
      return jsonResponse(getStocks());
    }
    if (path === 'portfolio') {
      return jsonResponse(buildPortfolio());
    }
    if (path === 'dashboard') {
      return jsonResponse(buildDashboard());
    }
    if (path === 'analysis') {
      return jsonResponse(buildAnalysis());
    }
    if (path === 'distribution') {
      return jsonResponse(buildDistribution());
    }

    return jsonResponse({ error: 'Invalid path' });
  } catch (err) {
    return jsonResponse({ error: err.message });
  }
}

function doPost(e) {
  const path = getPath(e);
  const payload = getPayload(e);

  try {
    if (path === 'transactions') {
      addTransaction(payload);
      return jsonResponse({ ok: true });
    }

    if (path === 'stocks') {
      upsertStock(payload);
      return jsonResponse({ ok: true });
    }

    if (path === 'refresh') {
      const portfolio = buildPortfolio();
      const dashboard = buildDashboardFromPortfolio(portfolio);
      return jsonResponse({ ok: true, dashboard: dashboard });
    }

    return jsonResponse({ error: 'Invalid path' });
  } catch (err) {
    return jsonResponse({ error: err.message });
  }
}

function getPath(e) {
  return String((e && e.parameter && e.parameter.path) || '').toLowerCase();
}

function getPayload(e) {
  const content = (e && e.postData && e.postData.contents) || '{}';
  return JSON.parse(content);
}

function getOrCreateSheet(name, headers) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
  }
  return sheet;
}

function ensureSheets() {
  getOrCreateSheet(SHEET_NAMES.transactions, ['id', 'date', 'symbol', 'name', 'type', 'price', 'qty', 'fee', 'amount', 'note']);
  getOrCreateSheet(SHEET_NAMES.stocks, ['symbol', 'name', 'market', 'industry']);
  getOrCreateSheet(SHEET_NAMES.portfolio, ['symbol', 'name', 'market', 'industry', 'shares', 'avg_cost', 'market_price', 'cost', 'market_value', 'profit', 'return_rate']);
  getOrCreateSheet(SHEET_NAMES.dashboard, ['total_invested', 'total_market_value', 'total_profit', 'total_return_rate', 'updated_at']);
}

function getStocks() {
  ensureSheets();
  const sheet = getOrCreateSheet(SHEET_NAMES.stocks, ['symbol', 'name', 'market', 'industry']);
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) return [];

  return values.slice(1)
    .filter((row) => String(row[0]).trim() !== '')
    .map((row) => ({
      symbol: String(row[0]).toUpperCase(),
      name: String(row[1] || ''),
      market: String(row[2] || ''),
      industry: String(row[3] || ''),
    }));
}

function upsertStock(payload) {
  ensureSheets();
  const sheet = getOrCreateSheet(SHEET_NAMES.stocks, ['symbol', 'name', 'market', 'industry']);
  const values = sheet.getDataRange().getValues();
  const symbol = String(payload.symbol || '').toUpperCase().trim();
  if (!symbol) throw new Error('symbol required');

  const rowData = [symbol, String(payload.name || ''), String(payload.market || ''), String(payload.industry || '')];

  for (let i = 1; i < values.length; i += 1) {
    if (String(values[i][0]).toUpperCase() === symbol) {
      sheet.getRange(i + 1, 1, 1, 4).setValues([rowData]);
      return;
    }
  }

  sheet.appendRow(rowData);
}

function getTransactions(filters) {
  ensureSheets();
  const sheet = getOrCreateSheet(SHEET_NAMES.transactions, ['id', 'date', 'symbol', 'name', 'type', 'price', 'qty', 'fee', 'amount', 'note']);
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) return [];

  const all = values.slice(1)
    .filter((row) => String(row[0]).trim() !== '')
    .map((row) => ({
      id: row[0],
      date: row[1],
      symbol: String(row[2]).toUpperCase(),
      name: String(row[3] || ''),
      type: String(row[4] || '').toUpperCase(),
      price: Number(row[5] || 0),
      qty: Number(row[6] || 0),
      fee: Number(row[7] || 0),
      amount: Number(row[8] || 0),
      note: String(row[9] || ''),
    }));

  return all.filter((item) => {
    if (filters.symbol && item.symbol !== String(filters.symbol).toUpperCase()) return false;
    if (filters.type && item.type !== String(filters.type).toUpperCase()) return false;
    if (filters.startDate && String(item.date) < String(filters.startDate)) return false;
    if (filters.endDate && String(item.date) > String(filters.endDate)) return false;
    return true;
  });
}

function addTransaction(payload) {
  ensureSheets();
  const sheet = getOrCreateSheet(SHEET_NAMES.transactions, ['id', 'date', 'symbol', 'name', 'type', 'price', 'qty', 'fee', 'amount', 'note']);

  const date = String(payload.date || '');
  const symbol = String(payload.symbol || '').toUpperCase().trim();
  const type = String(payload.type || '').toUpperCase();
  const price = Number(payload.price || 0);
  const qty = Number(payload.qty || 0);
  const fee = Number(payload.fee || 0);
  const note = String(payload.note || '');

  if (!date) throw new Error('date required');
  if (!symbol) throw new Error('symbol required');
  if (['BUY', 'SELL', 'CASH_DIV', 'STOCK_DIV'].indexOf(type) < 0) {
    throw new Error('type must be BUY/SELL/CASH_DIV/STOCK_DIV');
  }

  const stock = findStock(symbol);
  const name = stock ? stock.name : String(payload.name || '');

  let amount = 0;
  if (type === 'BUY') amount = (price * qty) + fee;
  if (type === 'SELL') amount = -(price * qty) + fee;
  if (type === 'CASH_DIV') amount = -(price * qty);
  if (type === 'STOCK_DIV') amount = 0;

  sheet.appendRow([
    Utilities.getUuid(),
    date,
    symbol,
    name,
    type,
    price,
    qty,
    fee,
    amount,
    note,
  ]);
}

function findStock(symbol) {
  const stocks = getStocks();
  for (let i = 0; i < stocks.length; i += 1) {
    if (stocks[i].symbol === symbol) return stocks[i];
  }
  return null;
}

function buildPortfolio() {
  const transactions = getTransactions({});
  const stockMap = {};
  const stocks = getStocks();
  stocks.forEach((s) => {
    stockMap[s.symbol] = s;
  });

  const map = {};

  transactions.forEach((t) => {
    if (!map[t.symbol]) {
      map[t.symbol] = {
        symbol: t.symbol,
        name: t.name || (stockMap[t.symbol] && stockMap[t.symbol].name) || '',
        market: (stockMap[t.symbol] && stockMap[t.symbol].market) || '',
        industry: (stockMap[t.symbol] && stockMap[t.symbol].industry) || '未分類',
        shares: 0,
        cost: 0,
        realized: 0,
      };
    }

    const row = map[t.symbol];

    if (t.type === 'BUY') {
      row.shares += t.qty;
      row.cost += (t.price * t.qty) + t.fee;
    } else if (t.type === 'SELL') {
      if (row.shares <= 0) return;
      const avgCost = row.cost / row.shares;
      const sellQty = Math.min(t.qty, row.shares);
      const reduceCost = avgCost * sellQty;
      const proceeds = (t.price * sellQty) - t.fee;
      row.realized += proceeds - reduceCost;
      row.shares -= sellQty;
      row.cost -= reduceCost;
    } else if (t.type === 'CASH_DIV') {
      row.realized += t.price * t.qty;
    } else if (t.type === 'STOCK_DIV') {
      row.shares += t.qty;
    }
  });

  const portfolio = Object.keys(map)
    .map((symbol) => {
      const row = map[symbol];
      if (row.shares <= 0) return null;

      const avgCost = row.shares > 0 ? row.cost / row.shares : 0;
      const marketPrice = getRealtimePrice(symbol);
      const marketValue = marketPrice * row.shares;
      const profit = marketValue - row.cost;
      const returnRate = row.cost > 0 ? profit / row.cost : 0;

      return {
        symbol: symbol,
        name: row.name,
        market: row.market,
        industry: row.industry,
        shares: Number(row.shares.toFixed(4)),
        avgCost: Number(avgCost.toFixed(4)),
        marketPrice: Number(marketPrice.toFixed(4)),
        cost: Number(row.cost.toFixed(4)),
        marketValue: Number(marketValue.toFixed(4)),
        profit: Number(profit.toFixed(4)),
        returnRate: Number(returnRate.toFixed(6)),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.symbol.localeCompare(b.symbol));

  writePortfolioSheet(portfolio);
  return portfolio;
}

function writePortfolioSheet(portfolio) {
  const sheet = getOrCreateSheet(SHEET_NAMES.portfolio, ['symbol', 'name', 'market', 'industry', 'shares', 'avg_cost', 'market_price', 'cost', 'market_value', 'profit', 'return_rate']);
  clearDataRows(sheet);

  if (portfolio.length === 0) return;

  const rows = portfolio.map((p) => [p.symbol, p.name, p.market, p.industry, p.shares, p.avgCost, p.marketPrice, p.cost, p.marketValue, p.profit, p.returnRate]);
  sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
}

function buildDashboard() {
  const portfolio = buildPortfolio();
  return buildDashboardFromPortfolio(portfolio);
}

function buildDashboardFromPortfolio(portfolio) {
  let totalInvested = 0;
  let totalMarketValue = 0;

  portfolio.forEach((p) => {
    totalInvested += p.cost;
    totalMarketValue += p.marketValue;
  });

  const totalProfit = totalMarketValue - totalInvested;
  const totalReturnRate = totalInvested > 0 ? totalProfit / totalInvested : 0;

  const data = {
    totalInvested: Number(totalInvested.toFixed(4)),
    totalMarketValue: Number(totalMarketValue.toFixed(4)),
    totalProfit: Number(totalProfit.toFixed(4)),
    totalReturnRate: Number(totalReturnRate.toFixed(6)),
    updatedAt: new Date().toISOString(),
  };

  writeDashboardSheet(data);
  return data;
}

function writeDashboardSheet(d) {
  const sheet = getOrCreateSheet(SHEET_NAMES.dashboard, ['total_invested', 'total_market_value', 'total_profit', 'total_return_rate', 'updated_at']);
  clearDataRows(sheet);
  sheet.appendRow([d.totalInvested, d.totalMarketValue, d.totalProfit, d.totalReturnRate, d.updatedAt]);
}

function buildDistribution() {
  const portfolio = buildPortfolio();
  const group = {};

  portfolio.forEach((p) => {
    const key = p.industry || '未分類';
    if (!group[key]) group[key] = 0;
    group[key] += p.marketValue;
  });

  return Object.keys(group).map((name) => ({
    name: name,
    value: Number(group[name].toFixed(4)),
  }));
}

function buildAnalysis() {
  const tx = getTransactions({});
  const sells = tx.filter((t) => t.type === 'SELL');

  let win = 0;
  let loss = 0;
  let sumReturn = 0;

  sells.forEach((s) => {
    const r = s.price > 0 ? (s.amount / (s.price * s.qty)) : 0;
    if (r >= 0) win += 1;
    else loss += 1;
    sumReturn += r;
  });

  const total = sells.length;
  const winRate = total > 0 ? win / total : 0;
  const avgReturn = total > 0 ? sumReturn / total : 0;

  const txByDate = tx.slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
  let equity = 0;
  let peak = 0;
  let maxDrawdown = 0;

  txByDate.forEach((t) => {
    equity -= t.amount;
    peak = Math.max(peak, equity);
    if (peak > 0) {
      const dd = (peak - equity) / peak;
      maxDrawdown = Math.max(maxDrawdown, dd);
    }
  });

  return {
    winRate: Number(winRate.toFixed(6)),
    avgReturn: Number(avgReturn.toFixed(6)),
    maxDrawdown: Number(maxDrawdown.toFixed(6)),
    tradeCount: total,
  };
}

function clearDataRows(sheet) {
  const last = sheet.getLastRow();
  if (last > 1) {
    sheet.getRange(2, 1, last - 1, sheet.getLastColumn()).clearContent();
  }
}

function getRealtimePrice(symbol) {
  const url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + encodeURIComponent(symbol) + '?interval=1m&range=1d';
  const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  const data = JSON.parse(response.getContentText());
  const result = data.chart && data.chart.result && data.chart.result[0];
  const quote = result && result.meta && result.meta.regularMarketPrice;
  return Number(quote || 0);
}

function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
