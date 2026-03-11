const SHEET_NAMES = {
  positions: 'positions',
  trades: 'trades',
};

function doGet(e) {
  const path = (e.parameter.path || '').toLowerCase();
  try {
    if (path === 'positions') {
      return jsonResponse(getPositions());
    }
    if (path === 'trades') {
      return jsonResponse(getTrades());
    }
    return jsonResponse({ error: 'Invalid path' }, 400);
  } catch (err) {
    return jsonResponse({ error: err.message }, 500);
  }
}

function doPost(e) {
  const path = (e.parameter.path || '').toLowerCase();
  const payload = JSON.parse(e.postData.contents || '{}');

  try {
    if (path === 'positions') {
      upsertPosition(payload);
      return jsonResponse({ ok: true });
    }

    if (path === 'trades') {
      addTrade(payload);
      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: 'Invalid path' }, 400);
  } catch (err) {
    return jsonResponse({ error: err.message }, 500);
  }
}

function doDelete(e) {
  const path = (e.parameter.path || '').toLowerCase();

  try {
    if (path.indexOf('positions/') === 0) {
      const symbol = path.replace('positions/', '').toUpperCase();
      deletePosition(symbol);
      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: 'Invalid path' }, 400);
  } catch (err) {
    return jsonResponse({ error: err.message }, 500);
  }
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

function getPositions() {
  const sheet = getOrCreateSheet(SHEET_NAMES.positions, ['symbol', 'name', 'shares', 'avgCost']);
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) return [];

  return values.slice(1).map((row) => {
    const symbol = String(row[0]).toUpperCase();
    const currentPrice = getRealtimePrice(symbol);
    return {
      symbol,
      name: row[1],
      shares: Number(row[2]),
      avgCost: Number(row[3]),
      currentPrice,
    };
  });
}

function getTrades() {
  const sheet = getOrCreateSheet(SHEET_NAMES.trades, ['symbol', 'shares', 'price', 'buyTime']);
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) return [];

  return values.slice(1).map((row) => {
    const symbol = String(row[0]).toUpperCase();
    return {
      symbol,
      shares: Number(row[1]),
      price: Number(row[2]),
      buyTime: row[3],
      currentPrice: getRealtimePrice(symbol),
    };
  });
}

function upsertPosition(payload) {
  const sheet = getOrCreateSheet(SHEET_NAMES.positions, ['symbol', 'name', 'shares', 'avgCost']);
  const values = sheet.getDataRange().getValues();
  const symbol = String(payload.symbol || '').toUpperCase();

  if (!symbol) throw new Error('symbol required');

  for (let i = 1; i < values.length; i += 1) {
    if (String(values[i][0]).toUpperCase() === symbol) {
      sheet.getRange(i + 1, 1, 1, 4).setValues([[symbol, payload.name || '', payload.shares, payload.avgCost]]);
      return;
    }
  }

  sheet.appendRow([symbol, payload.name || '', payload.shares, payload.avgCost]);
}

function addTrade(payload) {
  const sheet = getOrCreateSheet(SHEET_NAMES.trades, ['symbol', 'shares', 'price', 'buyTime']);
  const symbol = String(payload.symbol || '').toUpperCase();
  if (!symbol) throw new Error('symbol required');

  sheet.appendRow([symbol, payload.shares, payload.price, payload.buyTime]);
}

function deletePosition(symbol) {
  const sheet = getOrCreateSheet(SHEET_NAMES.positions, ['symbol', 'name', 'shares', 'avgCost']);
  const values = sheet.getDataRange().getValues();

  for (let i = 1; i < values.length; i += 1) {
    if (String(values[i][0]).toUpperCase() === symbol) {
      sheet.deleteRow(i + 1);
      return;
    }
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
