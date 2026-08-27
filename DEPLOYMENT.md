# v1.13.2 可上線版部署說明

## A. GitHub / Codespaces 準備

將此專案整個推到 GitHub repository。

Main file：

```text
app.py
```

請不要把真正的：

```text
.streamlit/secrets.toml
```

commit 到 GitHub；`.gitignore` 已排除。

---

## B. Google Sheets

本版預設連接：

```text
https://docs.google.com/spreadsheets/d/1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/edit?usp=sharing
```

worksheet：

```text
boxes
```

若將來更換 Sheet，不需要修改程式，直接在 Streamlit Secrets 覆蓋：

```toml
[box_store]
spreadsheet = "新的 Google Sheet URL"
worksheet = "boxes"
```

---

## C. Service Account

Google Sheets 需要讀寫權限。

1. 在 Google Cloud 建立 Service Account。
2. 建立 JSON key。
3. 找到 JSON 裡的 `client_email`。
4. 將 Google Sheet 分享給該 `client_email`。
5. 權限設定為「編輯者」。

---

## D. Streamlit Community Cloud Secrets

在 Streamlit Cloud：

```text
App
→ Settings
→ Secrets
```

依照：

```text
.streamlit/secrets.toml.example
```

貼入真正 Service Account 資料。

特別注意 `private_key` 要保留：

```text
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

---

## E. requirements.txt

本版 `requirements.txt` 已包含：

```text
streamlit
pandas
plotly
st-gsheets-connection
```

部署時不需要另外指定 online requirements。

---

## F. 第一次上線

第一次上線後建議：

1. 進入「ULD／箱子管理」。
2. 按「測試 Google Sheets 連線」。
3. 如果線上 Sheet 缺目前預設 ULD，按「補入缺少的預設 ULD」。
4. 檢查資料。
5. 按「儲存 ULD 資料」。

儲存後 Google Sheet 會轉成目前程式所需欄位結構，包括：

```text
box_id
name
l
w
h
max_weight
compatible_aircraft
compatible_zones
allow_center_load
center_positions
enabled
notes
```

---

## G. 本地 / Codespaces 暫時測試

正式版預設 Google Sheets。

若 Codespaces 尚未設定 Service Account，但想先跑本地資料：

```bash
export BOX_STORE_BACKEND=json
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

要恢復 Google Sheets：

```bash
unset BOX_STORE_BACKEND
```

或：

```bash
export BOX_STORE_BACKEND=gsheets
```

---

## H. 上線時的資料原則

`boxes.json` 仍保留在專案中，作為：

- 線下備援
- 預設 ULD 清單
- 開發測試

正式上線時的 ULD 修改以 Google Sheets 為準。
