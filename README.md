# Google Sheet 股票管理系統（HTML + Apps Script）

維持目前架構：
- 前端：`index.html` + `styles.css` + `app.js`
- 後端：`apps-script/Code.gs`
- 資料庫：Google Sheet

## 功能列表（最終版）

1. 新增交易（買入/賣出/現金股利/股票股利）
2. 股票資料庫（stock_list）
3. 持股統計（持股、平均成本、市值、損益、報酬率）
4. 即時股價
5. 投資總覽 Dashboard
6. 損益分析（勝率、平均報酬、最大回撤）
7. 歷史交易查詢（股票/日期/類型）
8. 圖表分析（產業分布圓餅圖）

## Google Sheet 資料表設計

系統會自動建立 4 個 Sheet：
- `transactions`：交易紀錄
- `stocks`：股票主檔
- `portfolio`：持股統計結果
- `dashboard`：總覽統計結果

## 主要欄位

### transactions
- id, date, symbol, name, type, price, qty, fee, amount, note

### stocks
- symbol, name, market, industry

## 使用步驟

1. 建立 Google Sheet。
2. 打開「擴充功能 → Apps Script」，貼上 `apps-script/Code.gs`。
3. 部署成 Web App（建議：任何知道連結的人可存取）。
4. 啟動前端：

```bash
python3 -m http.server 8080
```

5. 進入 `http://localhost:8080`，在底部 API 設定貼上 Apps Script `/exec` URL。

## 計算邏輯摘要

- 交易金額：
  - 買入：`price * qty + fee`
  - 賣出：`-(price * qty) + fee`
  - 現金股利：`-(price * qty)`
  - 股票股利：`0`
- 持股：`買入股數 - 賣出股數 + 股票股利`
- 平均成本：`成本 / 持股數`
- 未實現損益：`市值 - 成本`
- 報酬率：`(市值 - 成本) / 成本`

## 備註

- 幣值顯示統一為 `NTD$`。
- 前端每 5 分鐘會自動更新股價，同時保留手動更新按鈕。
