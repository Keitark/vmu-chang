# VMU-CHANG / VMU版スタックチャン

Dreamcast の Visual Memory Unit（VMU）**単体**で動く、ｽﾀｯｸﾁｬﾝの非公式ファン実装です。DC は VMU へのインストールに利用します。

48×32ドットのモノクロ画面にスタックチャンの顔と本体を描画し、瞬き・視線移動・口パク・感情表現・吹き出しを表示します。

## 操作

| VMUボタン | 表情・反応 |
|---|---|
| A | 口パク + `MNYA` |
| B | 笑顔 + ハート |
| ↑ | 笑顔 + `HI!` |
| ↓ | 眠そうな顔 + `ZZZ` |
| ← | 怒り顔 + `NO` |
| → | うれしい顔 + `YES` |
| MODE | VMUメニューへ戻る |
| SLEEP | スリープ |

## 現状と重要な注意点

**開発・検証途中のPoCです。**

- LC86K向けの `STACKCHN.VMS`、転送用 `STACKCHN.VMI` とソースコードを作成済みです。
- 自作の簡易LC86Kテストで描画・ボタン入力をチェックし、実機VMU単体での起動もユーザーから確認できました。各ボタンの反応とアニメーション速度の実機検証は未完了です。
- 旧候補のCD-Rは書き込み後の照合に成功しましたが、実機Dreamcastでは **SEGAロゴのあと停止**しました。
- CD-Rへの書き込み成功や簡易CPUテスト成功は、DreamcastのCDIが正常起動する保証にはなりません。
- **新しい `--hardware-startup` 候補は実機Dreamcastでブラウザー起動に成功しました。** 2026年10月15日、ユーザーの報告とテレビ画面の写真で確認しました。
- 同日の写真で、コントローラーA・スロット1のVMUに `STACKCHAN` の保存が完了したというブラウザーの表示も確認し、その後ユーザーから **VMU単体でも起動した** との報告がありました。VMU内の内容の読み戻し・ハッシュ照合は行っていません。

BOING と同じブートローダーを使い、ブラウザーのドライブ種別応答と Audio/Data のセクター位置を修正しています。新しい `--hardware-startup` 候補は、元のローダーのGD-ROM初期化処理、キャッシュ切り替えの修正、起動位置を示す色付きマーカーも追加しました。Flycast 2.7 の HLE BIOS と実機Dreamcastの両方でブラウザーが起動し、構造・全85ファイルの照合とCD-Rの書き込み後の全2セッション照合にも成功しました。初期化とキャッシュ遷移を同時に修正したため、以前の停止原因の厳密な切り分けは未完了です。再現手順と検証結果は [BOING ブートローダー版](docs/boing-vmu.md) を参照してください。

## ソースコード

顔だけを表示するシンプル版は [Stack-chan Face](face/README.md) を参照してください。ebazchan の丸い目と直線の口を48×32ドットに適応し、まばたきだけを加えた4ブロックの別プログラムです。元の版はそのまま残しています。新しい版はローカルの18項目チェックに合格していますが、実機VMUでの確認はこれからです。

`stackchan.s`（LC86Kアセンブリ）、`build_vms.py`、`make_art.py`、`smoke_test.py`、Windows用CDI構築スクリプト、および `STACKCHN.VMS` / `STACKCHN.VMI` を収録します。

- `python make_art.py` — ドット絵・フレーム素材を生成（Pillowが必要）
- `python build_vms.py` — VMS/VMIを作成
- `python smoke_test.py` — 簡易CPUテスト
- `BUILD_CDI.bat` — Windows上でVMU Disc Builderを用いてCDI作成を試みる（**起動未検証**）

詳細は [README_ja.md](README_ja.md) を参照してください。

## 参考・権利表記

- [スタックチャン](https://github.com/stack-chan/stack-chan)
- [M5Stack-Avatar](https://github.com/stack-chan/m5stack-avatar)（顔・表情のデザイン参考、MIT）
- [Waterbear](https://github.com/wtetzner/waterbear)
- [VMU Disc Builder](https://github.com/DerekPascarella/VMU-Disc-Builder)

こちらは公式の移植版ではありません。第三者由来の権利情報は `THIRD_PARTY_NOTICES.txt` に記載しています。
