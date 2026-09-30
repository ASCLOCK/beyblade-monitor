# 爆旋陀螺（Beyblade）香港網店新貨監測

定時掃描香港四間有賣 Beyblade 爆旋陀螺的網店，發現**新上架**或**補貨**時，自動透過 **Telegram** 傳訊息到你的手機。

## 監測的網店

| 網店 | 來源 | 狀態 |
|------|------|------|
| Last Chance Toy（lastchancetoy.com） | Shopify API | ✅ |
| T Club（tclub.com.hk） | Shopify API | ✅ |
| Toys"R"Us 香港（toysrus.com.hk） | 產品 Sitemap | ✅（僅偵測新上架） |
| Hobbyland 玩具模型倉（hobbylandeshop.com） | 後端 API | ✅ |

## 檔案說明

- `monitor.py` — 主程式（只用 Python 標準函式庫，**不用 pip 安裝任何套件**）
- `config.json` — 設定檔（Telegram Token、關鍵字、網店清單）
- `state.json` — 自動產生的狀態檔（記錄已見過的商品，用於判斷新貨/補貨）
- `start_loop.bat` — Windows 一鍵常駐執行（每 30 分鐘掃一次）

## 使用前準備

1. 安裝 **Python 3.8 以上**（Windows 到 python.org 下載安裝即可）。
2. 確認 `config.json` 裡的 `telegram.bot_token` 與 `telegram.chat_id` 已填好（已幫你填上）。

## 使用方式

在專案資料夾開啟命令列（PowerShell / cmd），執行：

```powershell
# 測試 Telegram 是否正常（會送一封測試訊息到手機）
python monitor.py --test

# 掃描並列出目前所有 Beyblade 商品（不通知、不改狀態）
python monitor.py --scan

# 執行一次（掃描 → 偵測新貨/補貨 → 通知 → 存狀態）
python monitor.py

# 常駐執行：每 30 分鐘掃一次（終端機要開著）
python monitor.py --loop 30
```

> 第一次執行只會「建立基準」並送一封啟動摘要，**不會**把現有商品當成新貨狂通知。之後每次執行，只有「新的商品出現」或「原本缺貨變有貨」才會通知。

## 讓它自動跑（推薦：Windows 排程）

> ✅ **已設定完成**：工作排程器內已建立「Beyblade Monitor」工作，每 30 分鐘自動執行一次。以下步驟僅供你需要重設或自行建立時參考。

常駐 `--loop` 需要一直開著視窗。更穩定的做法是用 **Windows 工作排程器**，每 30 分鐘執行一次：

1. 按 `Win + R`，輸入 `taskschd.msc` 開啟工作排程器。
2. 右側「建立工作」→ 名稱填 `Beyblade Monitor`。
3. 「觸發程序」分頁 → 新增 → 每天開始，勾選「重複工作每隔 **30 分鐘**」，持續時間「無限期」。
4. 「動作」分頁 → 新增 → 啟動程式：
   - 程式/指令碼：`C:\Users\lingc\AppData\Local\Python\pythoncore-3.14-64\python.exe`
   - 引數：`F:\app\beyblade-monitor\monitor.py`
   - 開始位置：`F:\app\beyblade-monitor`
5. 條件分頁：取消勾選「只有當電腦使用 AC 電源時才啟動」（若你想用電池也跑）。
6. 確定並儲存，之後可右鍵「執行」測試一次。

> 排程器裡的 python 路徑請以你電腦實際為準。在命令列執行 `where python` 即可查得。

## 自訂關鍵字

預設關鍵字已涵蓋 Beyblade X（BX／UX 編號、爆旋陀螺、ベイブレード、陀螺）。若要增減，編輯 `config.json`：

- `keywords` — 增加或移除關鍵字（英文不分大小寫）。
- `code_pattern` — 型號正規表示式。預設 `\b(BX|UX)[\-\s]?\d{1,2}\b`，只抓 Beyblade X 的 1~2 位數字型號，避開 Tomica 合金車的 3 位數編號。若你也想抓 Beyblade X 的 **CX** 系列，把 `(BX|UX)` 改成 `(BX|UX|CX)`（注意：會多抓到 Mazda CX 車款，建議同時在 `exclude_keywords` 加 `mazda`）。
- `exclude_keywords` — 排除關鍵字（避免誤判，例如 `tomica`、`mazda`）。
- `shops.<key>.enabled` — 設 `false` 可停用某間店。

## 新增其他網店

- **Shopify 網店**：在 `shops` 加入一項 `{"type": "shopify", "name": "...", "url": "https://...", "enabled": true}`。
- 其他平台需在 `monitor.py` 寫對應的擷取器（可參考 `scrape_hobbyland`）。

## 通知內容範例

```
🆕 新貨上架｜T Club
爆旋陀螺X BX-38 疾風軍刀 4-70TP
💰 價格：HKD 79.90
📦 狀態：有貨
🔗 https://www.tclub.com.hk/products/...
```

若商品有圖，會以圖片＋文字方式送出。

## 雲端部署（阿里云等 Linux 伺服器，24 小時常駐）

> ⚠️ **Telegram 在中國大陸被封鎖**：伺服器一定要選**香港**（或新加坡、海外）節點，否則收不到通知。若只能用大陸節點，需改用 Email／ntfy.sh／企業微信等通知方式。

1. 把整個資料夾上傳到伺服器（在你自己的 Windows 電腦執行）：

   ```powershell
   scp -r F:\app\beyblade-monitor  root@你的伺服器IP:/opt/
   ```

2. 登入伺服器測試：

   ```bash
   ssh root@你的伺服器IP
   cd /opt/beyblade-monitor
   python3 monitor.py --test     # 收到 Telegram 測試訊息即成功
   python3 monitor.py            # 建立基準狀態
   ```

3. 用 systemd 讓它常駐（開機自啟、掛掉自動重啟）：

   ```bash
   sudo bash /opt/beyblade-monitor/deploy/setup_linux.sh
   # 或手動：
   sudo cp /opt/beyblade-monitor/deploy/beyblade-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now beyblade-monitor
   ```

   常用指令：

   ```bash
   systemctl status beyblade-monitor   # 查看狀態
   journalctl -u beyblade-monitor -f   # 即時看日誌
   systemctl stop beyblade-monitor     # 停止
   ```

4. 不想用 systemd，也可用 cron（`crontab -e` 加入這行，每 30 分鐘一次）：

   ```cron
   */30 * * * * cd /opt/beyblade-monitor && /usr/bin/python3 monitor.py >> /opt/beyblade-monitor/monitor.log 2>&1
   ```

免費方案：Oracle Cloud Always Free（需信用卡、常缺貨）、GitHub Actions 的 cron（免費，見下節）。最省事是香港區的輕量伺服器（約每月 ¥24 起）。

## GitHub Actions 部署（完全免費、零伺服器、零信用卡）

已幫你準備好 `.github/workflows/monitor.yml`，每 30 分鐘自動跑一次，狀態檔 `state.json` 會自動提交回倉庫保存（也順便避免排程因 60 天無 commit 被停用）。

### 步驟

1. **建立 GitHub 倉庫**（建議設為 **Private**）：
   - 到 github.com 建立新倉庫，例如 `beyblade-monitor`。
   - 把你電腦上的專案資料夾推上去：

     ```powershell
     cd F:\app\beyblade-monitor
     git init
     git add .
     git commit -m "init beyblade monitor"
     git branch -M main
     git remote add origin https://github.com/你的帳號/beyblade-monitor.git
     git push -u origin main
     ```

2. **設定 Secrets**（Token 不進程式碼）：
   - 在倉庫頁面 → **Settings → Secrets and variables → Actions → New repository secret**，新增兩個：
     - `TELEGRAM_BOT_TOKEN` = 你的 Bot Token
     - `TELEGRAM_CHAT_ID` = 你的 Chat ID

3. **啟用排程**：推到 `main` 分支後，workflow 會自動依 cron 每 30 分鐘執行。也可到 **Actions** 頁面選「Beyblade Monitor」→「Run workflow」手動觸發一次測試。

### 注意

- 排程用 **UTC** 時間；GitHub 的排程可能有數分鐘延遲（正常）。
- **Private 倉庫**免費額度 2000 分鐘/月：每 30 分鐘一次約 1440 分鐘/月，足夠。**Public 倉庫**則完全不限分鐘，但 `state.json`（你監測的商品清單）會公開——內容不含 Token，若不在意可設 Public 換取不限額度。
- ⚠️ 若你之前在本機設了 **Windows 工作排程**，記得停用它，否則會兩邊同時通知。

## 注意事項

- `config.json` 的 Telegram Token 已留空（避免洩漏）；實際 Token 請放 GitHub Secrets 或環境變數，**不要**填回並提交。
- 每間店掃描需數秒（Toys"R"Us 的 Sitemap 較大約 8MB），一次完整掃描約 10 秒。
- 網店偶爾會擋爬蟲或改版；若某間店掃描失敗，程式會記錄錯誤並繼續掃其他店，不會中斷。
- Toys"R"Us 的 Sitemap 沒有庫存資訊，因此該店只能偵測「新上架」，無法偵測「補貨」。

## 常見問題

- **收不到通知**：先跑 `python monitor.py --test`，確認 Telegram Token 與 Chat ID 正確，且你曾先對你的 Bot 傳過訊息（或把 Bot 加進群組）。
- **拿到 Chat ID**：對 Telegram 的 `@userinfobot` 傳訊息即可取得你的個人 ID。
- **建 Bot Token**：對 `@BotFather` 傳 `/newbot` 建立，取得形如 `123456:ABC...` 的 Token。
