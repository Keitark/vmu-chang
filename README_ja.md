# VMU Stack-chan / VMU版スタックチャン

ドリームキャストの Visual Memory Unit（VMU）**単体**で動く小型アバターです。DC本体はゲームをVMUに書き込むためだけに使用します。シューティングゲームではありません。

## 画面と表情

M5Stack-Avatar / ｽﾀｯｸﾁｬﾝの実機表情に近づけるため、黒いスクリーンに丸い2つの目と細い口、四角い筐体、3つのボタン、下部の2本の足を48×32モノクロドットで再現しています。VMU液晶では色・実サーボ首振り・音声合成は再現できないため、1ドット単位の首の上下左右アニメーションと口パクで代用しています。

| VMU単体ボタン | 反応 | 吹き出し |
|---|---|---|
| A | 口パクしておしゃべり | MNYA |
| B | にっこり | ♥（ハート） |
| 十字キー ↑ | 笑顔 | HI! |
| 十字キー ↓ | 眠い目 | ZZZ |
| 十字キー ← | 怒った目 | NO |
| 十字キー → | うれしい目 | YES |
| MODE | VMUメニューに戻る | — |
| SLEEP | VMUのスリープ | — |

放置すると自動でまばたき、視線移動、呼吸風の上下動、微笑みが発生します。全32フレーム。A/B/十字キーを押したときはボタンを離しても約数秒間動作します。外部ネットワーク接続やLLMは使いません。

## 実機へのインストール手順（実験中・起動問題は未解決）

2026-10-14時点では、元のData/Data CDIはFlycast 2.7のHLE BIOSでSEGAロゴからブラウザまで起動しましたが、利用者のMIL-CD対応・日本版DreamcastではSEGAロゴ前に本体メニューへ戻りました。CDのPC読戻し照合は成功しています。後から作成したAudio/Data変換版はSEGAロゴで停止しており、代替として使用できません。詳細は [docs/boot-status.md](docs/boot-status.md) を参照してください。

以下は本来想定した転送手順です。実機での起動・VMUへの転送成功を保証するものではありません。

必要物: VMU、Dreamcastとコントローラー、CD-Rと書き込みドライブ、Windows PC、インターネット接続。

1. このZIPをWindows PCへ展開します。
2. `BUILD_CDI.bat` を実行します。
3. 初回だけ [VMU Disc Builder v1.1](https://github.com/DerekPascarella/VMU-Disc-Builder/releases/tag/1.1) がGitHubから取得されます。
4. `VMU_STACKCHAN.cdi` が作られます。デフォルトではダミーファイルを追加して約550 MiBのファイルシステムを作るため、CDI全体はさらに大きくなります。今回の元CDIは659,785,440バイトです。大きさは実機起動成功の証拠ではありません。
5. ImgBurnなどのCDI対応書き込みツールで**イメージとして**CD-Rに焼きます（ファイルを通常のデータCDとして書き込むのではありません）。
6. DreamcastをそのCDから起動し、VMU Disc Builder由来のブラウザ型メニューで `STACKCHAN` を選び、VMUにダウンロードします。
7. CDを終え、VMUをコントローラーから取り外してVMU本体のメニューから `VMU STACK-CHAN` を実行します。

ダミーファイルの省略（CDIのサイズを小さくする、ODE向け）:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_cdi_windows.ps1 -NoDummy
```

すでに別途VMU Disc Builderを入れている場合は、`STACKCHN.VMS` と `STACKCHN.VMI` を同じ `save_files` フォルダに配置して直接ビルドしても構いません。

## ファイル

- `STACKCHN.VMS` — VMU LC86Kネイティブゲーム（8192バイト、16ブロック）
- `STACKCHN.VMI` — VMUダウンロード用のメタ情報（108バイト）
- `stackchan.s` — ネイティブLC86Kアセンブリソース
- `make_art.py` — 48×32アニメーションとアイコンを作るPythonコード（Pillowが必要）
- `build_vms.py` — アセンブル、VMS/VMIパッケージング（Python標準ライブラリのみ）
- `smoke_test.py` — 独立した簡易LC86K CPUシミュレーションテスト
- `THIRD_PARTY_NOTICES.txt` — 原作者へのクレジットとライセンス表記
- `build_cdi_windows.ps1`, `BUILD_CDI.bat` — 実機MIL-CD用イメージ構築
- `preview.gif`, `showcase.png` — 表示の雰囲気（実機LCDカラーではない擬似表示）

ソースから作り直すには、Python 3とPillowを導入後、`python make_art.py` → `python build_vms.py` → `python smoke_test.py` の順に実行します。`build_vms.py`内のアセンブリテンプレートが編集元であり、このフォルダ内のVMS/VMIバイナリ、テスト用`symbols.json`、生成された`stackchan.s`を更新します。`stackchan.s`はWaterbear互換の命令書式でも出力します。

## 検証と注意事項

- 独自の最小LC86K命令インタプリタ上で、206フレームの画面RAMへの転送・6ボタンの反応・まばたき/視線移動を検証済みです。
- **Dreamcast実機での元ディスクの起動は失敗しており、VMU実機での起動・描画は未検証です。** Flycast HLEの起動成功、PCでのCD照合成功、簡易LC86Kテストは、実機の起動成功を意味しません。
- `BUILD_CDI.bat` / PowerShellは利用者のWindows上で第三者ツールをダウンロードして実行します。実行前に内容と上流配布元を確認してください。
- `VMS` 内にサウンドやAI音声は含まれません。小さな「MNYA」吹き出しによる擬似おしゃべりです。
- 画面デザインはｽﾀｯｸﾁｬﾝの公開情報を参考にした非公式の低解像度ファン実装です。

## 参照元 / クレジット

- スタックチャン（オープンロボット）: https://github.com/stack-chan/stack-chan
- M5Stack-Avatar（顔・まばたき・表情の原設計、MIT）: https://github.com/stack-chan/m5stack-avatar
- Waterbear VMU アセンブラ/命令書式: https://github.com/wtetzner/waterbear
- VMU Disc Builder（CDI作成の第三者ツール）: https://github.com/DerekPascarella/VMU-Disc-Builder
- VMU VMI format: https://mirror.tcb13.com/mc.pp.se/dc/vms/vmi.html

本作品は上記プロジェクトの公式移植版ではありません。上流のゲーム・ファームウェアや音声アセットは同梱していません。
