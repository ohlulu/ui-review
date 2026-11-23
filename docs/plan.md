---
summary: Approved design for ui-review — agent/tool contract, site, recordings, retention, server, phasing, and why each choice was made (Chinese)
read_when:
  - Changing the notes.json / capture.json / manifest contract or the publish checks
  - Changing retention, the server, or the web shell layout
  - Planning v1b recordings or a project adapter
---

# UI Review 站 — 規劃書

狀態：已核准，v0 與 v1a 一起做。§11 決定：刪除照全域規則走 trash（選項 a），名稱沿用 `ui-review` / `uireview`。

2026-11 增補：screens 模式與互動 run（`uireview start` + `shot --run`），manifest 升到 schema 2，見 §13。

v0 結果：通過，維持單一 Python server，不改 nginx（§8 翻盤條件關閉）。依據：owner 在 air 上用網頁驗證播放、切換、裁決都沒問題；iOS Safari（simulator）實測影片可以 inline 播放，Range 回 206；從 iPhone 送出的裁決 POST 全部 200。Chromium 系瀏覽器開了 Secure DNS 時解析不到 tailnet 名稱，在 air 本機改用 `http://127.0.0.1:8788/`。
依據：兩輪 consultant（A / B）、air 上的實測 probe、另一個 iOS 專案既有的 nightly 報告與錄影實作。

## 1. 要解決什麼

你在外面（iPhone 走 SSH，或 mbp）時，看不到 agent 在 air 上做的 UI 改動。目標是：

- 一個固定網址，打開就看到「待你判斷」的改動，幾分鐘內在手機上做出 ✅ / ❌ 決定。
- 每個改動有 before / after 截圖比對、放大到該看的地方、agent 的說明；動畫或時序類改動附錄影。
- 網頁是固定模版，agent 不寫 HTML，只填文字。
- 舊東西會自動清掉，但沒判斷過的永遠不會被誤刪。

非目標（v1 不做）：每個 commit 自動拍一排截圖、TestFlight、Linear 同步、推播通知、HTTPS、air 關機時還能看。

## 2. 整體長相

```
iPhone / mbp ──tailnet──▶ air:8787 (tailscale serve, tailnet only)
                              │
                              ▼
                  127.0.0.1:8788  uireview serve   (LaunchAgent, KeepAlive)
                  ├── /            固定 shell：index.html + app.js + app.css
                  ├── /runs/<id>/  manifest.json + webp + mp4（只讀）
                  ├── /api/runs    即時掃描列出所有 run
                  └── POST /api/runs/<id>/verdict  寫入裁決

agent（在 air 的 app 專案 pane）
  make review-base     → 開工時存 before .app
  make review-capture  → 收工時 before / after 兩個 build 各跑同一份 recipe
  填 notes.json        → 只寫文字
  uireview publish     → 驗證、裁切、壓縮、上架，印出網址
```

## 3. 元件與擺放

| 元件 | 位置 | 內容 |
|---|---|---|
| 工具本體 | 新 repo `ui-review` | 單一 stdlib Python CLI `uireview`（目標 ≤ 700 行）、`web/` 固定 shell、tests |
| 安裝 | `uireview install` | CLI symlink 到 `~/.local/bin`、寫 LaunchAgent plist、檢查 tailscale serve |
| 資料 | `~/.local/state/ui-review/` | `base/`（before .app）、`work/`（原始 PNG、AX）、`runs/`（上架內容） |
| App adapter | app 專案 repo | `make review-base`、`make review-capture RECIPE=…`、`scripts/review-lib.sh`（launch args、等 anchor、狀態列、旋轉）、專案的 verify skill 加一節 |
| Skill | 本 repo `skills/ui-review/SKILL.md`，以 local pi package 安裝（`pi install <checkout>`） | 什麼時候用、流程、怎麼拿 compact help；註明只在 air |

Skill 跟工具同 repo、不放 `~/.pi/agent/skills`：改指令時 skill 和 CLI 在同一個 commit 裡一起變；沒有 checkout 的機器（mbp）載入時直接略過這個 package，不會出現一份能讀但不能用的 skill。
不放 `~/.pi/agent/bin`：dotfiles 的 discovery 會把 symlink 追蹤進去，到 mbp 變成斷掉的連結。
不放 app 專案的 `.logs/`：專案的 log 清理腳本看 mtime，`cp -Rc` 保留 mtime，base .app 會在 build 七天後被 `make run` 順手清掉。

## 4. Agent 和工具的分工（「只塞內容」怎麼落實）

工具寫、agent 不碰：
- `capture.json`：每張截圖的 sha256、時間、udid、方向、AX snapshot、當下安裝 app 的 hash（涵蓋 `<App>.debug.dylib`；Debug 主執行檔只是 58 KB 的 stub）。
- before / after 由工具判定：裝的是 base hash 就是 before，是本次 build 就是 after。agent 無法宣稱。

agent 只填 `notes.json`（工具先產骨架）：
- run 層：`title`、`judge`（需要你判斷的問題）、`checks`（頁面標示為 agent 回報）。
- card 層：`what`（改了什麼）、`look[]`（請看哪裡）、`question?`、`roi[]`（accessibility id，或逃生用的 rect；預設留空，只有全圖縮到手機寬度看不出來的細節才加，大部分卡靠全圖加文字就夠判斷）。

`uireview publish` 嚴格驗證：未知欄位、空的必填、引用不存在的 card、不是 capture 產生的圖，一律失敗。notes 只能用 card id 引用截圖，不能給檔案路徑，這就是「拒收舊圖」的機制。這是防誤用，不是防蓄意偽造。

ROI：兩側各自用 AX frame 解析，取聯集加 padding，套到兩側，裁出同位置同尺寸的圖。只有一側有該元素時用另一側的框；兩側都沒有就 publish 失敗。

截圖穩定：`uireview shot` 連拍到連續兩張 pixel 相同才收，超過上限標 `UNSTABLE`。recipe run 的狀態列固定 09:41（互動 run 不覆寫，見 §13）。

## 5. 網站

首頁（單頁）：
- run id 是口頭溝通的代號：每列最前面用標題大小顯示，網站一律顯示大寫（`R18`，跟卡片 `C01` 一致）；磁碟、URL、CLI 輸出維持小寫，CLI 兩種大小寫都收。
- 上段「待裁決」，新到舊。每列：run id、標題、project（多個 project 且沒篩選時）、round、時間、還有幾張待看、一個關閉鍵（✕）；超過 14 天標 Stale。待裁決有兩個以上時，標題旁有「全部關閉」，只關目前專案篩選看得到的 run；有關失敗的會在列表上方列出 run id。關閉不跳確認框，改成底部 toast「已關閉 R3 · 復原」，8 秒內可復原（指標或焦點停在 toast 上時暫停計時），復原只重新開啟這個 toast 關掉的 run。誤關的代價只是一次復原，確認框反而每次都多一步。
- 下段「已裁決」，每列寫結果：全部通過 / n 張要改 / 已關閉 / 無變更 / 被 rN 取代。
- project 篩選只在超過一個 project 時出現。

Run 頁（`/#<run-id>`，沿用 r00-probe 的卡片）：
- 頁首：需要你判斷、多久前拍的、狀態提示（已關閉、被取代、重做、A/A）；agent 回報的檢查收合；base / after 的 build hash 放在頁尾「技術細節」。
- 每張卡：`C02`、狀態 tag（Changed / New / Unchanged 收合 / Motion；screens run 的卡不顯示 tag）、改了什麼、請看哪裡、連拍不穩時的提示、Before / After 切換、1:1 ROI、錄影（若有）、通過 ✅ / 要改 ❌ / 有疑問 ❓ + 備註。
- 放大（2026-11）：點截圖或 ROI 開全螢幕 viewer（`<dialog>`，參考 maestro-lang-ios nightly 報告的截圖 viewer）。viewer 裡點圖切 Before / After，切到哪一邊會同步回卡片上的切換；左右鍵或底部按鈕跳到同一個 run 的上一張 / 下一張（略過收合的 Unchanged 卡），點圖以外的地方、✕ 或 Esc 關閉，關閉後焦點回到最後看的那張圖。點圖原本是切換，改成放大是因為手機上 iPad 截圖太小看不清；卡片上的切換改由上方的 Before / After 鍵負責。
- 按「關閉這個 run」成功後回到列表，同樣出現可復原的 toast；「重新開啟」留在 run 頁。
- 版面：手機單欄由上往下（文字 → 圖 → 裁決）。視窗 ≥ 1024px 時 run 頁加寬到 1240px，每張卡左欄放截圖、錄影、ROI，右欄 340px 放文字和裁決，看圖時不用上下捲動找按鈕；截圖高度限制在一個視窗內。首頁維持 720px。桌面瀏覽器（滑鼠指標）視窗 ≥ 1536px 時整個頁面以 CSS `zoom: 1.5` 放大，等同瀏覽器縮放 150%；門檻讓放大後仍有 1024px，寬版面照樣成立。Before / After 不做並排，因為差異要靠閃換才看得出來。
- 外觀（2026-11 改版）：只有 light mode，Geist + PingFang TC，Phosphor icon。Before / After 切換刻意不做轉場：差異要靠瞬間閃換才看得出來。只有第一次載入有很輕的進場（上移 6px、2px blur 轉清楚，0.8 秒內），截圖第一次載入時從 skeleton 轉清楚；換頁、切換、裁決都不播放大動畫。
- 裁決存在 server（`verdict.json`），iPhone 和 mbp 看到同一份。存成功才顯示「已儲存」。
- 最後一張卡下方有「全部通過」：只把還沒裁決的卡一次標成 ✅（一個 request），已經按過 ❌ / ❓ 的卡不覆蓋；部分已裁決時按鈕寫「剩下 N 張全部通過」，沒有未裁決的卡就隱藏。不跳 confirm：每張卡事後都能個別改回來。
- 「複製裁決」拿掉，只留一條路：你按完後在 SSH 說一句「r07 看完」，agent 跑 `uireview verdict r07` 讀回。

模版版本：manifest 帶 `schema`（目前 2），shell 遇到不認得的版本顯示「不支援」，不寫相容層；舊 run 會在保留期內自然消失。

## 6. 錄影

何時錄：只在改動牽涉 animation、transition、手勢、時序（loading、toast、鍵盤避讓）時。靜態版面和文案不錄。每個 run 最多 3 支。

怎麼錄：`uireview clip <card> -- <操作指令>` 包住整段，agent 不管 pid，也沒有獨立的 stop 指令可忘。
1. 先清掉這台 sim 殘留的 recorder。
2. 啟動 `simctl io recordVideo`，讀 stderr 等 `Recording started`（simctl help 有寫明，上限 10 秒）。
3. 執行操作，上限 20 秒。
4. SIGINT，等 10 秒；再一次 SIGINT；仍不結束才 SIGKILL，標記 `needs_reboot`，只讓這張卡的影片失敗。
5. wrapper 自己被 SIGTERM / SIGHUP 時也走第 4 步。
6. `ffprobe` 驗證輸出。

這修正了既有 verify 流程 `recordVideo &` + `kill -INT` 的寫法；另一個 iOS 專案的 ADR 記錄過那種寫法 3 次卡 2 次。consultant B 在 sim 上實測 handshake 12 次全部正常收尾。

壓縮：1× 速度（3× 是 maestro 看失敗用的，判斷動畫手感要原速），CFR 60、1280 寬、CRF 約 24、faststart、無聲。開頭靜止段裁到動作前 0.3 秒，結尾補定格。before 和 after 用 ffmpeg 上下疊成一支，同步是天生的；手機上一個 `<video playsinline loop>`，可切 0.5× / 0.25× 慢放。

## 7. 清除

| 對象 | 什麼時候清 |
|---|---|
| 已裁決 run（每張卡都有 ✅ / ❌、或被下一個 round 取代、或你按關閉） | 裁決後 7 天 |
| 待裁決 run | 永不自動清；14 天後標 STALE |
| `work/<run>`（原始 PNG、AX） | 裁決當下 |
| 原始錄影 | 壓縮完當場取代，不留 |
| base .app（約 100 MB，APFS clone） | task 被接受或關閉時；或閒置 14 天 |
| 沒 publish 的草稿 | 3 天 |

時機：每次 publish 時順便跑，不另設排程（沒有 agent 活動就沒有新東西）。`uireview prune --dry-run` 先看再刪；首頁和 `doctor` 顯示總用量。不設容量上限。

刪除方式：見 §11 第 1 題，需要你決定。

## 8. Server 與部署

- `uireview serve`：stdlib `ThreadingHTTPServer`，綁 `127.0.0.1:8788`，支援 Range（iOS Safari 播 mp4 必要；`python3 -m http.server` 已實測不支援）。
- LaunchAgent `RunAtLoad` + `KeepAlive`；登入後自動起來。
- 沿用已設好的 `tailscale serve --http=8787 → 127.0.0.1:8788`（已實測 tailnet 200、區網 refused）。
- verdict POST 的防護：run id regex、run 必須存在、固定 schema（含型別）、8 KB 上限、只收 `application/json`、檢查 Origin / Host。
- 除了 `/healthz`，所有 request 的 Host 必須在固定清單內（loopback 加 tailnet 名稱）。只比對 Origin == Host 擋不住 DNS rebinding：攻擊網域重新解析到 127.0.0.1 後，兩者會相等。HTML 加 `frame-ancestors 'none'` 防止被嵌入。
- `uireview doctor`：launchctl 狀態、`/healthz`、Range 回 206、serve 設定正確。`publish` 印網址前先跑一次，agent 不會交出死連結。
- 翻盤條件：iPhone 播影片不穩，就改 nginx 管靜態檔、Python 只留 API。

## 9. 信任保護（重點：假可比比畫錯更危險）

- 截圖只能由 `shot` 產生，帶 hash 和時間，publish 驗證。
- before / after 由安裝的 binary hash 判定。
- 忘了存 base：`capture` 直接失敗；只看新畫面要明講 `--no-base`（或用 `start`），不湊舊圖。
- 用同一份 recipe、同 fixture、同語言、同 tier、同方向，連續跑兩個 build。
- 腳本中途死掉：`trap` 把 after build 裝回去並比對 hash，避免之後驗到錯的 build。
- Gate 1 截圖是設計目標，不是 before，不做 diff；Gate 1 的狀態用 screens run 發佈（§13）。

## 10. 分期

v0（實作前的手機 probe，約 5 分鐘你的時間）
- 把 8788 換成支援 Range 的 server，放一支合成的上下疊 mp4，加一顆 verdict 按鈕。
- 你用 iPhone 開一次：影片能不能 inline 播、切換順不順、按鈕能不能存。
- 這是整個設計唯一完全沒驗證的環節，不過就不往下做。

v1a — 截圖端到端
- ui-review repo：CLI（base save / capture / shot / publish / verdict / prune / serve / doctor / install）+ 固定 shell + tests。
- App adapter + 專案 verify skill 一節 + skill。
- 驗收：同一個 build 跑兩次 capture，0 張 CHANGED（A/A）；拿一個真實 app UI task 從 base 到你在手機上裁決走完一輪；故意塞舊 PNG 被拒。

v1b — 錄影
- `clip` + 壓縮 + 上下疊 + player。
- 驗收：專用 sim 連續 10 次極短錄影含中途取消，不卡、下一次照錄。

延後：per-commit archive、Linear mirror、通知或喚醒 pane、Gate 1 目標當第三張圖、其他 repo 的 recipe（介面已是 udid / bundle / app / recipe，屆時只需寫 recipe）、HTTPS、容量上限。

## 11. 需要你決定

1. 清除的刪法：全域規則是「一律 trash」。Trash 不會自動清空，丟進去不會釋放空間。選項：(a) 照規則 trash，prune 印出丟了多少；(b) 只對 `~/.local/state/ui-review/` 這個工具自管的目錄允許直接刪除。
2. 名稱：`ui-review` / `uireview` 和 `/review`、`review_plan` 等既有 review 工具字面相近。可以照用，或換一個（例如 `shotdeck`、`uidiff`）。
3. 整份規劃是否核准，或哪些地方要改。

## 12. 兩位 consultant 的分歧與我的取捨

| 題目 | A | B | 採用 | 理由 |
|---|---|---|---|---|
| Server | nginx + Python API 兩個 daemon | 單一 Python（含 Range） | B | 一個 process；B 實測 Range 206、AVFoundation 可播；iPhone probe 不過再改 nginx |
| 首頁列表 | 可重建的 index.json + publish lock | server 即時掃描 | B | server 本來就在，少一份要同步的索引 |
| 影片呈現 | 上下兩支各自播 | ffmpeg 疊成一支 | B | 同步不用寫 JS；iPad 橫向疊兩張剛好接近直立手機比例 |
| 影片參數 | 960w、VFR | 1280w、CFR 60、裁頭補尾 | B | 裁頭補尾需要 CFR；靜止畫面錄出來只有 1 frame |
| 何時算結案 | 必須明確關閉 | 全卡有裁決或被取代或關閉 | B（❓ 不算） | 少一個動作，❓ 仍保留 |
| 刪除 | 請你核准限定直接刪除 | 維持 trash | 交給你 | 這是你的規則 |
| 複製裁決 | 保留當備援 | 拿掉 | 拿掉 | 只留一條路；http 頁面複製本來就不穩 |
| 排程清理 | publish + 每日 launchd | 只在 publish | 只在 publish | 沒活動就沒新增量 |

兩位一致的部分（直接採用）：固定 shell + 版本化 manifest、agent 只填文字、base 放工具自己的資料目錄、待裁決永不自動刪、simctl + handshake 錄影、1× 不是 3×、裁決存在 server、先截圖後錄影。

## 13. screens run：只看新畫面（2026-11 增補）

起因：某個 app 專案的一個 session 做完一個沒走 Gate 1 prototype 的版面改動，回報裡寫「請看 03／04 的截圖」。截圖在 air 的 `.logs/verify/`，你要往上捲 TUI 才看得到，手機上完全看不到；每張圖要看哪裡也只散在報告的半句話裡。那個 session 有列出 ui-review skill，但沒載入，原因有三：那個專案自己的規則把 Gate 1 截圖和完成證據導到 `.logs/`；skill 寫明不收 Gate 1；工具的第一步要求開工時先存 base，可是那個 session 一開始只是診斷。

要補的是「單張狀態、看設計」的情境：Gate 1 prototype、新畫面、驗證時一路操作出來的狀態。這些情境沒有 before，或 before 根本不是判斷重點。

設計：
- run 分兩種模式，manifest 帶 `mode`。compare 就是原本的前後對照；screens 只有 after，每張卡各自裁決，狀態是 `SCREEN`，網頁不顯示 tag、也不顯示「只有 After」，因為這就是這個 run 的本意。
- `NO BASELINE` 拿掉。原本它同時代表「忘了存 base」和「本來就只想看新的」，前者是錯誤、後者是正常用法，混在一起只會讓警告失去意義。現在 `capture` 找不到 base 就失敗，要 after-only 得明講 `--no-base`。
- 互動 run：`uireview start` 記下模擬器上目前安裝的 build hash，agent 邊操作邊跑 `uireview shot <slug> --run rN`。截圖仍然只由 `shot` 產生、帶 hash，`publish` 照舊驗證，所以「拒收舊圖」的保證不變。安裝的 app 一換，後面的 `shot` 就拒收。每次 `shot` 會把新卡片接到 `notes.json` 尾端，已經填的內容保留。
- `--run` 只收 `start` 開的 run：recipe run 的 before / after 由 `capture` 依序安裝決定，從外面補拍會產生一張沒有對照的卡。
- 互動 run 不能有 before：要有 before 就要在 base build 上重跑同一段操作，這正是 recipe 存在的理由。
- 互動 run 不覆寫狀態列：沒有成對比較，09:41 只是好看；覆寫了就得有人記得還原，`start` 沒有結束指令可以做這件事。

取捨：考慮過讓 agent 把現成的 PNG 交給 `publish`，這樣接 app 專案既有的 verify 流程最省事，但等於放棄「只有 `shot` 能產生截圖」這條防線。`shot --run` 一樣接得上互動流程，只是每個狀態多打一行指令。

manifest 格式變了（`mode`、`SCREEN`、拿掉 `NO BASELINE`），`SCHEMA` 升到 2；改版時 air 上的 4 個 run 都已裁決，顯示「不支援」直到保留期清掉。

App 專案端：Gate 1 的狀態截圖改用 screens run 發佈；完成報告裡要你判斷的畫面改給卡片連結，不再引用截圖檔名。Gate 2 的 fidelity 對照需要 Gate 1 截圖留得比 run 的保留期久，所以 Gate 1 run 發佈後把 PNG 複製到 `.logs/gate1/<feature>/`。
