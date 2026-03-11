# Google Sheet 股票追蹤程式（HTML 前端）

目前維持原本架構：
- 前端：`index.html` + `styles.css` + `app.js`
- 後端：`apps-script/Code.gs`
- 資料庫：Google Sheet

## 功能分頁

### 分頁 1：【交易紀錄表】（輸入區）
欄位：
- 日期
- 標的代碼
- 動作（買/賣）
- 單價
- 股數
- 手續費
- 投入總額（前端自動計算）

用途：精準紀錄每一筆低接/扣款（買入）或賣出，並含手續費成本。

### 分頁 2：【資產儀表板】（決策區）
從【交易紀錄表】自動彙整並顯示：
- 自動股價（即時報價）
- 持有股數
- 平均成本（損益兩平點）
- 未實現損益

## 使用步驟

1. 建立 Google Sheet。
2. 開啟「擴充功能 → Apps Script」，貼上 `apps-script/Code.gs`。
3. 部署為 Web App（建議權限：「任何知道連結的人」）。
4. 前端啟動：

```bash
python3 -m http.server 8080
```

5. 開啟 `http://localhost:8080`，在頁面最下方「API 設定」貼上 Web App URL。

## 備註

- 股票代號請用 Yahoo Finance 格式，例如：`2330.TW`、`AAPL`。
- 若 Apps Script 有更新，記得重新部署並使用新的 `/exec` URL。

- 幣值顯示已統一為 `NTD$`。
