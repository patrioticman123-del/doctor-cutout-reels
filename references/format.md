# 資料格式與執行

使用者只給主題，AI 負責查證並完成 JSON。`examples/template.json` 是尚未指定疾病的通用讀劇範本。

| 欄位 | 意義 |
|---|---|
| `title`, `topic` | 不可空白 |
| `content_type` | `medical` 或 `template`，醫療片必須有來源與 claims |
| `brand` | 畫面標識，最多 14 字，不杜撰診所名 |
| `names` | doctor/alo/mei/narrator 的顯示名稱，各最多 8 字 |
| `footer` | 底部短句，最多 28 字 |
| `voices` | doctor/alo/mei/narrator 各含 edge 與 sapi 聲音名稱 |
| `sources` | id/title/url/accessed（YYYY-MM-DD）/supports |
| `scenes` | 2–14 幕，30–60 秒通常用 7–12 幕 |

每幕欄位：

- `speaker`：doctor / alo / mei / narrator。至少 75% 幕是人物對話。
- `cast`：同框角色 ID 陣列，2–3 人，限 doctor/alo/mei；發言者必須出鏡。學生不等同成人患者。
- `text`：完整配音；`headline`：字卡最多 26 字；`beat`：故事功能。
- `setting`：classroom 教室／schoolyard 小學校園／street 街道。
- `shot`：wide / doctor / alo / mei / punch，記錄對話焦點。**現成引擎鎖定人物尺寸與腳底基準，不因 shot 放大發言者或縮小聽者。** 全身畫面固定尺度，對話焦點以標示、嘴型和小動作表達。
- `motion`：nod 上下點頭／shake 左右搖頭／still 靜止；`hold`：句後停頓 0.1–2 秒。
- `action`、`reaction`：供審稿的表演與接話說明，必填。只描述引擎支援的動作；更複雜動作先擴充並重新審稿。
- `claims`：來源 ID 陣列。純劇情可空；醫療說法須對應來源。
- `audio`：選填，以本 JSON 所在目錄為基準的錄音路徑，files 模式每幕必填。
- `teaching`：選填，預設 `{"mode":"dialogue"}`。其他 mode 為 `blackboard`、`bone_model`、`quiz`、`comparison`，須填 `title`（1–16 字）和 `points`（1–3 個、每個最多 16 字）。comparison 必須兩個重點，bone_model 只用一個重點，保留模型空間；長字串仍須通過實際排字檢查。教具幕使用兩位同尺度人物分站兩側，讓黑板或模型在中間可見。

```json
"teaching": {"mode":"blackboard", "title":"本集關鍵關係", "points":["第一個重點", "下一個重點"]}
```

黑板有條列、箭頭與指示棒；骨頭教具幕實際畫出桌子、支架和一般長骨形狀模型（示意）；quiz 顯示選項，comparison 顯示並列卡。教具資訊會出現在完整腳本中。特定關節、脊椎或病灶圖仍需依來源另做模型，不能把通用骨頭圖當成精確解剖教學。人物尺寸跨演法保持一致。

## 兩階段命令

```sh
# 預設：只做腳本與分鏡，無 TTS、音樂、影片
python scripts/render.py episode.json --out build/my-episode

# 交稿後等待使用者確認，再使用 draft.json 的 revision
python scripts/render.py episode.json --out build/my-episode --render --approved-hash CONFIRMED_REVISION --voice edge
```

確認碼來自 episode JSON、角色資產和引擎檔案雜湊。任何相關修改都會使舊版失效；旗標是版本檢查，AI 不能自行當作使用者確認。只改文字腳本時務必同步 JSON，重新生成草稿。未收到明確確認前停在分鏡階段。

`--check` 只檢查資料與排字。`--width 540 --fps 12` 可在確認後輸出低解析度影片草稿；預設 1080/24。寬須為 18 的倍數。`--font /path/to/NotoSansCJK-Regular.ttc` 指定本機中文字體，無可用中文字體就報錯。

## 聲音後端

- Windows 預設 sapi；其他平台預設 edge。服務失敗會報錯，不靜默換成靜音。
- sapi 使用本機 System.Speech，優先 pwsh、否則 powershell.exe。預設醫師 Microsoft Zhiwei、阿洛 Microsoft Hanhan Desktop、美芳 Microsoft Yating；不同 PowerShell 能看見的聲音可能不同。使用相同 shell 執行 `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices().VoiceInfo` 查詢；找不到就修改 voices 或明確選其他後端。
- edge 透過第三方 edge-tts 用戶端使用線上服務，對話文字會上傳，不需 API key；預設 YunJheNeural/HsiaoChenNeural/HsiaoYuNeural 台灣華語。可能失敗或聲音變動；`edge-tts --list-voices` 可查詢。
- files 接任何 ffmpeg 能解碼的音檔，轉成 24 kHz mono PCM16。程式不做語音辨識，須自行確認錄音與 text 一致。

音訊快取按台詞、聲音設定與輸入音檔內容雜湊；修改後不會誤用舊配音。實測時長不在 30–60 秒就報錯，保留快取供修稿。原創程序配樂會降低人聲期間音量，punch 停頓留白。

## 輸出

第一階段：`script.md`、`storyboard.html`、`storyboard.jpg`、`frames/`、`episode.json`、`draft.json`。分鏡使用靜態預覽，秒數按字數估算；不是已完成的影片，沒有配音。

確認後：`episode.mp4`（H.264/AAC、yuv420p）、`episode.srt`、`preview.html`、`manifest.json`、`voice.wav`、`music.wav`、`mix.wav`、`audio/` 快取。保留第一階段腳本與靜態分鏡，不覆寫已審的 storyboard；成片抽幀另存 `render-storyboard.jpg`，便於比對。播放器需與 MP4 同目錄。嘴型為音量開合，字幕按實際音長比例切段，非逐音素或逐字時間戳。
