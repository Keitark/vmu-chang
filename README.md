# VMU-CHANG / VMU版スタックチャン

Dreamcast の Visual Memory Unit（VMU）**単体**で動く、ｽﾀｯｸﾁｬﾝの非公式ファン実装です。DC は VMU へのインストールに利用します。

[English documentation](README_EN.md)

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
- 自作の簡易LC86Kテストで描画・ボタン入力をチェックしましたが、**実機VMUでの動作確認は未完了**です。
- 元のData/Data CDIは、利用者のMIL-CD対応・日本版DreamcastではSEGAロゴ前に本体メニューへ戻りました。一方、Flycast 2.7のHLE BIOSではSEGAロゴからブラウザまで起動しています。
- 後から作成したAudio/Data変換版は、実機とFlycastの両方でSEGAロゴ後に停止しました。この変換版は代替として使用できません。詳細は [起動調査](docs/boot-status.md) を参照してください。
- CD-Rへの書き込み成功や簡易CPUテスト成功は、DreamcastのCDIが正常起動する保証にはなりません。
- **動作確認済みの `.cdi` は現時点では提供していません。** 繰り返しCD-Rに書き込む前に、ブート処理とFlycastでの動作確認が必要です。

## ソースコード

`stackchan.s`（生成されたLC86Kアセンブリ）、`build_vms.py`、`make_art.py`、`smoke_test.py`、Windows用CDI構築スクリプト、および `STACKCHN.VMS` / `STACKCHN.VMI` を収録します。アセンブリの編集元は`build_vms.py`内のテンプレートです。

- `python make_art.py` — ドット絵・フレーム素材を生成（Pillowが必要）
- `python build_vms.py` — VMS/VMIを作成
- `python smoke_test.py` — 簡易CPUテスト
- `BUILD_CDI.bat` — Windows上でVMU Disc Builderを用いてCDI作成を試みる（**実機起動問題は未解決**）

2026-10-14の再ビルドでは、VMS/VMIが元の配布ファイルとバイト単位で一致し、簡易テストは206フレーム・1,018,376命令と6ボタンの反応を検証しました。[ローカル検証結果](docs/local-validation.md)

詳細は [README_ja.md](README_ja.md) を参照してください。

## 参考・権利表記

- [スタックチャン](https://github.com/stack-chan/stack-chan)
- [M5Stack-Avatar](https://github.com/stack-chan/m5stack-avatar)（顔・表情のデザイン参考、MIT）
- [Waterbear](https://github.com/wtetzner/waterbear)
- [VMU Disc Builder](https://github.com/DerekPascarella/VMU-Disc-Builder)

こちらは公式の移植版ではありません。第三者由来の権利情報は `THIRD_PARTY_NOTICES.txt` に記載しています。
