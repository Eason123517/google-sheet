# Google Sheet 股票追蹤程式（HTML 前端）

這個專案符合你的需求：

1. 可新增、修改、移除持有股票。
2. 會顯示即時報價（透過 Apps Script 後端查 Yahoo Finance）。
3. 可紀錄每次買入，並顯示每筆交易損益、買入時間、股數。
4. 會計算總損益。
5. 介面以簡單直觀為主。

## 檔案說明

- `index.html`：前端主畫面
- `styles.css`：樣式
- `app.js`：前端邏輯與 API 串接
- `apps-script/Code.gs`：部署到 Google Apps Script 的後端程式

## 使用步驟

### 1) 建立 Google Sheet

建立一份新的 Google Sheet（例如命名 `stock-tracker`）。

### 2) 建立 Apps Script

1. 在 Google Sheet 點選「擴充功能」→「Apps Script」。
2. 把 `apps-script/Code.gs` 的內容貼上並儲存。
3. 點選「部署」→「新增部署」→ 類型選「網路應用程式」。
4. 執行身分可選你自己；存取權限建議「任何知道連結的人」。
5. 部署後複製 Web App URL。

### 3) 設定前端 API

你可以直接在頁面上方的「API 設定」貼上 Web App URL，按「儲存並測試連線」。

> 系統會將 URL 存在瀏覽器 `localStorage`，不用每次重填。

### 4) 啟動前端

在專案目錄執行：

```bash
python3 -m http.server 8080
```

然後打開 `http://localhost:8080`。

## 備註

- 股票代號建議使用 Yahoo Finance 格式，例如：
  - 台股：`2330.TW`
  - 美股：`AAPL`
- 目前幣別以 USD 顯示（你可自行調整 `app.js` 的 `currency`）。


## 常見問題

- 若出現「載入失敗」，請確認：
  1. Apps Script 已重新部署最新版。
  2. 部署權限為「任何知道連結的人」。
  3. 前端 API URL 為 `/exec` 結尾。
