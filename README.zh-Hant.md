# Community AI Compute｜社區 AI 算力

**讓共享算力擴大 AI 的可及性，為人類共同利益而公開開發。**

[English](README.md) · [參與討論](https://github.com/Andylaw95/community-ai-compute/discussions) · [貢獻指南](CONTRIBUTING.md)

我們希望讓人們自願分享電腦的閒置資源，完成有用的 AI 工作，幫助學生、研究者、獨立開發者及公共利益專案取得算力。參與者應能選擇貢獻時段與程度，隨時暫停或退出；工作完成並通過驗證後，才記錄貢獻。公平報酬、可分享及自用的算力額度，是後續共同研究的方向。

**目前是可執行的本機協調原型。**三個 CPU 程序在同一台電腦處理合成灰階影像統計，透過 loopback HTTP 接工，中央完整重算後寫入 SQLite。這不是 AI 模型推論、多機 GPU 運算或已上線的算力市場。

## 一個指令試跑

使用 macOS／Linux 及 Python 3.12；Windows 尚未支援及驗證。不需要安裝第三方依賴、下載模型、建立帳戶或使用付費 API。

```bash
git clone https://github.com/Andylaw95/community-ai-compute.git
cd community-ai-compute
python3 -m examples.quickstart
```

執行即表示同意這次小型 CPU 示範工作。程式會建立臨時伺服器、三個工作程序與資料庫，處理 96 張合成影像／6 個分片，驗證完成、重複提交與衝突處理，輸出 JSON 後清理。

應看見 `status: completed`、`accepted_images: 96`、`demo_credits_without_monetary_value: 96`，以及所有程序已停止、臨時資料庫已移除。示範點沒有現金或兌換價值。

## 互動工作台

```bash
python3 -m prototype.run --port 8765
```

開啟 **http://127.0.0.1:8765**，勾選同意、選擇設定並按「套用設定」，再「提交批次」。可查看工作程序、帳本、取回 JSON、暫停貢獻及注入故障。

在啟動終端機按 **Ctrl+C** 才會完全關閉伺服器與工作程序；只關閉瀏覽器不會停止。沒有安裝背景服務或開機自動啟動。資料預設保留於 `.runtime/demo.sqlite`；可用 `--db .runtime/another-demo.sqlite` 開始新的資料庫。不要把此服務轉發到公網。

## 已驗證與未實作

已實作分片、租約、三個 OS 程序、錯誤拒絕、有界重試、程序退出重派、重送去重、一次入帳及同意／暫停控制。公開準備時重跑 **15 項功能測試，全部通過**；詳見[驗證報告](docs/VALIDATION.md)。

「模擬前景遊戲」只測退避邏輯，並非真的偵測遊戲。百分比是每程序合作式工作時間預算，不是整機或 GPU 的硬限制。GPU、多台電腦、公網、AI 模型、機密運算、正式支付、可兌換額度及代幣都尚未實作。

## 一起找出值得做的下一步

我們需要協助選定一種有真實需求、非敏感、可獨立分片的 AI 工作，找出可負擔的驗證方法，並建立保護參與者與資料的設計。也歡迎重現測試、翻譯、改善可用性及指出不成立的假設。

請在[討論區](https://github.com/Andylaw95/community-ai-compute/discussions)分享使用情境、證據及替代方案，或從 [good first issue](https://github.com/Andylaw95/community-ai-compute/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22good%20first%20issue%22) 開始。英文及繁體中文均歡迎，不需要持有昂貴 GPU。

原始程式及專案自撰文件使用 [Apache-2.0](LICENSE)。研究論文、模型、資料及其他專案保留各自授權。這是使用 AI 協助建立的早期專案；目前不宣稱已有合作夥伴、客戶、非牟利機構資格、成本或節能優勢。
