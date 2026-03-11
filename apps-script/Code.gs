const SHEET_NAMES = {
  trades: 'trades',
};

function doGet(e) {
  const path = getPath(e);
  try {
    if (path === 'trades') {
      return jsonResponse(getTrades());
    }
    if (path === 'dashboard') {
      return jsonResponse(getDashboard());
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
    if (path === 'trades') {
      addTrade(payload);
      return jsonResponse({ ok: true });
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

function getTrades() {
  const headers = ['date', 'symbol', 'action', 'price', 'shares', 'fee', 'total'];
  const sheet = getOrCreateSheet(SHEET_NAMES.trades, headers);
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) return [];

  return values.slice(1).map((row) => ({
    date: row[0],
    symbol: String(row[1]).toUpperCase(),
    action: String(row[2]).toUpperCase(),
    price: Number(row[3]),
    shares: Number(row[4]),
    fee: Number(row[5]),
    total: Number(row[6]),
  }));
}

function addTrade(payload) {
  const headers = ['date', 'symbol', 'action', 'price', 'shares', 'fee', 'total'];
  const sheet = getOrCreateSheet(SHEET_NAMES.trades, headers);

  const date = String(payload.date || '');
  const symbol = String(payload.symbol || '').toUpperCase();
  const action = String(payload.action || '').toUpperCase();

  if (!date) throw new Error('date required');
  if (!symbol) throw new Error('symbol required');
  if (action !== 'BUY' && action !== 'SELL') throw new Error('action must be BUY/SELL');

  sheet.appendRow([
    date,
    symbol,
    action,
    Number(payload.price || 0),
    Number(payload.shares || 0),
    Number(payload.fee || 0),
    Number(payload.total || 0),
  ]);
}

function getDashboard() {
  const trades = getTrades();
  const bySymbol = {};

  trades.forEach((trade) => {
    const symbol = trade.symbol;
    if (!bySymbol[symbol]) {
      bySymbol[symbol] = { shares: 0, costBasis: 0 };
    }

    const row = bySymbol[symbol];
    const shares = Number(trade.shares);
    const price = Number(trade.price);
    const fee = Number(trade.fee);

    if (trade.action === 'BUY') {
      row.shares += shares;
      row.costBasis += (shares * price) + fee;
    } else {
      if (row.shares <= 0) return;
      const avgCost = row.costBasis / row.shares;
      const sellShares = Math.min(shares, row.shares);
      row.shares -= sellShares;
      row.costBasis -= sellShares * avgCost;
      row.costBasis = Math.max(0, row.costBasis - fee);
    }
  });

  return Object.keys(bySymbol)
    .map((symbol) => {
      const row = bySymbol[symbol];
      if (row.shares <= 0) return null;

      const avgCost = row.costBasis / row.shares;
      const currentPrice = getRealtimePrice(symbol);
      const unrealizedPnl = (currentPrice - avgCost) * row.shares;

      return {
        symbol: symbol,
        shares: Number(row.shares.toFixed(4)),
        avgCost: Number(avgCost.toFixed(4)),
        currentPrice: Number(currentPrice.toFixed(4)),
        unrealizedPnl: Number(unrealizedPnl.toFixed(4)),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
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
