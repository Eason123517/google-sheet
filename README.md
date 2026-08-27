# 3D 貨物排列系統 v1.13.9 — 獨立快速尺寸轉換頁








## v1.13.9

### 快速尺寸轉換改為獨立頁面

功能選單新增：

```text
📝 快速尺寸轉換
```

不再塞在「貨物資料」頁面中。

功能選單目前為：

```text
🏠 起始頁
📝 快速尺寸轉換
🧱 貨物資料
🚀 自動裝載
🧰 ULD／箱子管理
```

側邊欄選項加大為卡片式點選區域，並加入功能說明。

### ID 改為固定 ID

原本：

```text
ID 前綴 = CARGO
→ CARGO001
→ CARGO002
```

已取消。

現在輸入：

```text
ID = 09673823
```

該次貼入的所有不同尺寸列都會使用：

```text
ID = 09673823
```

不自行增加流水號。

### 多批 ID 累加

快速轉換的「帶入貨物資料」改為累加模式：

```text
ID 09673823
→ 5 件
→ 帶入

ID 90138473
→ 10 件
→ 再帶入

結果：
09673823 保留
90138473 往下新增
總件數 = 15
```

預設 ID 為：

```text
A
```

轉換頁上方會即時顯示：

```text
目前累積 ID 數
目前累積資料列
目前累積總件數
```

仍可：

```text
下載本批 CSV
```

帶入成功後也可：

```text
下載目前全部貨物 CSV
```

## v1.13.8 快速尺寸轉換器

「貨物資料」頁新增快速文字轉換。

支援以下格式：

```text
121*102*147*1
121x102x147x1
121X102X147X1
121×102×147×1
121 * 102 * 147 * 1
121 102 147 1
```

全部固定解讀為：

```text
長 × 寬 × 高 × 數量
```

操作流程：

```text
收到尺寸文字
↓
直接貼進程式
↓
自動解析
↓
檢查錯誤行
↓
帶入貨物資料 / 下載 CSV
↓
A333 / B777 計算
```

轉換後預設：

```text
ID：CARGO001、CARGO002...
名稱：貨物001、貨物002...
AGT：可在轉換器中選填
BUP：FALSE
總重量：0
水平旋轉：TRUE
垂直旋轉：FALSE
不能疊：FALSE
```

若有任何格式錯誤，程式會列出原始行號、內容與原因，
並暫停「帶入」與「下載」避免漏貨。

## v1.13.7

### C.F. 顯示精度

A333 與 B777 的 `C.F.` 改為顯示到小數點後 1 位。

例如：

```text
123.4
```

### 3D 圖下方顯示

A333 與 B777 的 3D 圖下方左側改為依序顯示：

```text
目前貨物最大 長
目前貨物最大 寬
目前貨物最大 高
C.F.
```

`C.F.` 會放在「目前貨物最大 高」的右側。

計算公式維持：

```text
Σ(長 × 寬 × 高 / 6000 / 4.72)
```

因 Packing Engine 已將數量展開為單件，因此與原始公式
`長 × 寬 × 高 × 件數 / 6000 / 4.72` 加總結果相同。

## v1.13.6

### 96 盤位名稱

96 不再顯示為「中央裝載」。

96 是：

```text
機尾中間96專用位置
```

它只是實體位置在機尾中間，不屬於一般中央裝載模式。

因此 B777 摘要表中：

```text
Surface = 機尾中間96專用位置
中央裝載盤位數 = -
```

### C.F.

A333 與 B777 的每 ULD / Loading Surface 摘要新增：

```text
C.F.
```

計算公式：

```text
每件貨物：
長 × 寬 × 高 × 件數 / 6000 / 4.72

每個 ULD 的 C.F.：
將該 ULD 內所有貨物 C.F. 加總
```

Packing engine 內貨物已展開為單件，所以實作等價於：

```text
Σ(placement.L × placement.W × placement.H / 6000 / 4.72)
```

顯示至小數點後 2 位。

## v1.13.5 TRUE/FALSE 欄位同步

針對 Google Sheet：

```text
allow_center_load
enabled
```

兩個布林欄位修正。

儲存時直接驗證 `GSheetsConnection.update()` 回傳的 DataFrame，
不再以「寫入後立即 read」作成功判斷，因此 Google Sheet 已成功更新時不會再出現假失敗。

載入時會清除 read cache，且 ULD `data_editor` 的 widget key 加入 Google Sheet 資料 fingerprint。
因此 Google Sheet TRUE/FALSE 改變後，重新載入會建立新的 checkbox state。

ULD 管理頁新增：

```text
↻ 重新載入 Google Sheets
```

## v1.13.4 Google Sheets 快取修正

v1.13.3 寫入後立刻使用 `conn.read()` 回讀驗證。

`st-gsheets-connection` 的 `read()` 使用 Streamlit `cache_data`，
因此可能發生：

```text
Google Sheet 實際已更新
↓
程式立即回讀
↓
讀到 update 前的舊快取
↓
誤判 118 allow_center_load 未同步
```

v1.13.4 改成：

```text
conn.update()
↓
st.cache_data.clear()
↓
重新讀取
↓
必要時短暫重試
↓
確認 allow_center_load / center_positions / enabled
```

因此不會因舊快取造成假失敗訊息。

## v1.13.3 Google Sheets 儲存修正

96 尺寸修正為 `317 × 243 × 243 cm`。

上一版「儲存 ULD 資料」沒有同步的主因，是 96 被程式驗證成高度必須為 234 cm。
只要表格中的 96 是 243 cm，整份 ULD 驗證就會失敗，因此 `save_boxes()` 根本不會執行。
「補入缺少的預設 ULD」走的是直接寫入流程，所以仍可成功。

Google Sheet 現在會使用 `allow_center_load` 欄位保存「可中央裝載」。
舊 Sheet 若缺少該欄，程式會自動建立並預設 FALSE。
勾選後按「儲存 ULD 資料」，TRUE/FALSE 會寫回 Google Sheets，下次直接讀回。

## v1.13.2 Google Sheets 可上線版

本版保留目前所有裝載功能，僅將正式資料來源切回 Google Sheets。

預設：

```text
BOX_STORE_BACKEND = gsheets
```

ULD／箱子管理的讀取與儲存會直接同步到：

```text
Google Sheets / boxes worksheet
```

若要暫時使用線下資料：

```bash
export BOX_STORE_BACKEND=json
```

完整部署方式請參考：

```text
DEPLOYMENT.md
```





## v1.13 B777 目前貨物最大尺寸

B777 自動裝載頁，在選擇某一個 ULD / Loading Surface 後，
會顯示：

```text
目前貨物最大長
目前貨物最大寬
目前貨物最大高
```

定義與 A333 頁面的外緣尺寸概念一致：

```text
長 = max(X + L)
寬 = 貨物實際橫向最左至最右外緣範圍
高 = max(Z + H)
```

單位皆為 cm。

B777 的「寬」使用 aircraft lateral Y 座標計算，
因此中央裝載、114 專用位置、尾端 96 專用位置
都會依其實際橫向位置取得正確使用寬度。

## v1.12 盤位圖顯示方式

B777 上艙盤位圖改成與實際 Loading Sheet 類似的橫向閱讀方式：

```text
左側 = 機頭
右側 = 機尾
```

所有位置放在同一張橫向盤位圖中：

```text
114-F1
114-F2
    ↓
118 等效盤位 01~11
（上列 R / 下列 L）
    ↓
114-R1
114-R2
    ↓
96-T
```

### 114

114 不再另外畫在第三列。

114 為中央專用位置，因此在圖中會：

```text
跨在 L / R 兩列中央
```

機頭 2 個、機尾 2 個。

### 96

96-T 位於：

```text
整張圖最右側
= 機尾最末端
```

同樣是中央專用位置，會跨在左右兩列中間顯示。

這只調整盤位圖呈現方式，
不改變既有 114 / 96 / PGA / 118 的裝載規則。

## v1.11 位置修正

### 114

114 不畫在左／右 118 盤位列。

實際邏輯改為：

```text
機頭：114-F1、114-F2
↓
中段：118 等效盤位，左右各 11
↓
機尾：114-R1、114-R2
↓
最後方：96-T
```

114 的四個位置皆是「中央專用位置」，
不是左側或右側 118 盤位。

### 尾端 96

每架 B777 機尾最後方只有一個唯一 96 盤位：

```text
L = 317 cm
W = 243 cm
H = 243 cm
```

位置：

```text
機尾中央
位於兩個後方 114 位置之後
```

規則：

- 每架只有 1 個。
- 只能放 96。
- 96 不能放到一般 118 等效盤位。
- 不使用一般「本次中央裝載」開關。
- `allow_center_load` 保持 `false`。
- 96 尺寸目前確認為 317×243×243 cm。

## v1.10 B777 上艙盤位規則

### 118 等效盤位

每架 B777 上貨艙最多：

```text
22 個 118 等效盤位
= 左側 11
+ 右側 11
```

目前正式 station / bay 名稱尚未提供，因此畫面暫用：

```text
01 ~ 11
```

避免把 B-M contour 的 12 個字母位置直接誤當成 11 個實體 118 盤位。

### PGA

```text
單側 PGA
→ 占同側 2 個連續 118 盤位

中央裝載 PGA
→ 占 4 個 118 盤位
→ 左右各 2 個
→ 仍使用 2 個同尺寸 PGA
```

PGA 的 `center_positions` 固定應為 `4`。

### 114

已建立 114 特殊規則支援：

```text
L = 310 cm
W = 236 cm
最大高度 = 140 cm
```

114 只能使用：

```text
114-F1
114-F2
114-R1
114-R2
```

共前後 4 個專用位置。

這 4 個位置不會分配給其他 ULD。

目前尚未取得 114 的最大載重，因此不自行加入 `boxes.json`。
使用者之後新增 `box_id=114` 並填入最大載重後，
程式會自動套用 114 專用位置與 140 cm 高度規則。

114 的頭尾精細 contour 尚待後續圖片，本版不誤用 B-M contour，
只使用已確認的固定 140 cm 高度上限。

### 上艙限定

以下 ULD 僅允許：

```text
B777_UPPER_BM
```

- 118
- PGA
- 114

ULD 管理若設定到其他區域，儲存時會顯示錯誤。


## v1.9.1 修正

修正 `dataframe_to_items()` 中的：

```text
NameError: name 'item_id' is not defined
```

現在會在每列資料開始時先建立：

```python
item_id = str(r["ID"]).strip()
```

並同時用於：

```text
Item.item_id
Item.batch_id
```

因此 B777 / A333 自動裝載都能正常建立以原始 ID 為基礎的 BUP 批次。

## BUP 改為依 ID 判斷

v1.9 不再以 AGT／公司作 BUP 分組。

規則：

```text
相同 ID = 同一批貨
```

同一個 ID 可以出現在多列，而且每列尺寸可以不同。

只要相同 ID 的任一列：

```text
BUP = TRUE
```

則該 ID 的所有貨物都會視為同一個 BUP 批次。

例如：

| ID | AGT | 尺寸 | BUP |
|---|---|---|---|
| A001 | A公司 | 100×80×50 | TRUE |
| A001 | A公司 | 120×90×70 | FALSE |
| A002 | A公司 | 110×90×60 | FALSE |
| B001 | B公司 | 90×90×50 | FALSE |

結果：

```text
A001
→ 兩列全部視為同一 BUP 批次
→ 可以使用 1 個或多個 ULD
→ 這些 ULD 不會放 A002 / B001

A002 + B001
→ 沒有 BUP
→ 仍可互相混裝
```

因此同一 AGT 可以同時有：

```text
部分 ID = BUP
其他 ID = 一般混裝
```

---

## AGT

舊版「群組」欄位改名為：

```text
AGT
```

AGT 只用來記錄公司／代理資訊。

BUP 不使用 AGT 作分組依據。

CSV 仍相容舊欄位：

```text
群組
公司
客戶
```

匯入後會轉成：

```text
AGT
```

---

## 相同 ID 多列

v1.9 修正 unit ID 產生方式。

例如：

```text
ID = A001
第一列 qty=2
第二列 qty=3
```

展開後會是：

```text
A001-001
A001-002
A001-003
A001-004
A001-005
```

不會因為相同 ID 出現在多列而產生重複 unit ID。

---

## 預設 boxes.json

每次新版專案預設放入：

| box_id | name | L | W | H | max_weight | aircraft | zone | center_positions |
|---|---|---:|---:|---:|---:|---|---|---:|
| 64 | PMC | 318 | 244 | 160 | 6800 | A333 | A333_GENERIC | 2 |
| PLA | PLA | 318 | 153 | 160 | 3175 | A333 | A333_GENERIC | 2 |
| 118 | 118 | 310 | 236 | 300 | 5000 | B777 | B777_UPPER_BM | 2 |
| 96 | 96 | 317 | 243 | 243 | 5000 | B777 | B777_UPPER_BM | 2 |
| PGA | PGA | 606 | 244 | 300 | 13680 | B777 | B777_UPPER_BM | 4 |
| AKE | AKE | 156 | 153 | 160 | 1588 | A333 | A333_GENERIC | 2 |
| PMC | PMC | 318 | 244 | 160 | 6800 | B777 | B777_UPPER_BM | 2 |

`enabled` 全部預設為 `true`。

由於目前尚未確認哪些 B777 ULD 可以中央裝載：

```text
allow_center_load
```

本版預設全部為：

```text
false
```

請在「ULD／箱子管理」逐一勾選確認可中央裝載的 ULD。

---

## 執行

GitHub Codespaces：

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

然後從 Codespaces 的 `PORTS` 開啟 8501。
