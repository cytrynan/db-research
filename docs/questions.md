---
type: Question Set
description: 型判定と検索品質の測定に使う質問20問（K が実際にくろこへ投げる形）。4型のラベルと正解の所在（ファイル・節）。個人データの値は書かない＝正解は「どこにあるか」だけ
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T09:10:00+09:00 }
status: draft
---

# 質問セット（20問）

> 出典: `~/.claude/references/INDEX.md` のトリガー語・横断トピック・各ファイルの節見出しから、K が日常的に投げる形に起こした（K指示 2026-09-29「references から20問全部作って」）。
> **正解は「どのファイルのどの節か」だけ**を書く。値（金額・型番・日付の中身）は本ファイルに書かない（リポは private でも外部ホスティングのため）。
> `expected` の `references/...` は取り込み後の `rel_path`。②は bench 時に SQL で算出した値を正とする（固定値を焼き込まない）。

## 内訳
| 型 | 問数 | 狙い |
|---|---|---|
| ① find | 10 | トリガー語で当たる質問（5）＋言い換え・横断で当たりにくい質問（5） |
| ② count | 4 | OKF メタデータの集計（ビューで答える） |
| ③ asof | 4 | 「いつ分離／決定したか」「◯月時点はどうだったか」 |
| ④ overview | 2 | 複数ファイルにまたがる全体観 |

## 質問

| # | 質問 | 型 | 期待（所在／算出） | 備考 |
|---|---|---|---|---|
| Q01 | 花粉症の薬とサプリ、何を飲んでるんだっけ | find | `references/health.md` §基本 | トリガー語直撃 |
| Q02 | メガネの度数どこに書いた？ | find | `references/health.md` §視力・メガネ | 同上 |
| Q03 | ネスプレッソのカプセル、好みと在庫は | find | `references/preferences.md`（好み）＋ `references/home.md` §消耗品の在庫 | 横断トピック。正解2ファイル |
| Q04 | バイトの締め日と給料日は | find | `references/work.md` §概要 | トリガー語直撃 |
| Q05 | 就活で候補にしている職種は | find | `references/work.md` §キャリア方針 | 同上 |
| Q06 | 目が悪くなってきた気がする。前の記録どこ | find | `references/health.md` §視力・メガネ | **言い換え**（「視力」「度数」を含まない） |
| Q07 | 深煎りが好きって書いたのどこだっけ | find | `references/preferences.md` | 語句一致はあるが節が不明 |
| Q08 | 家にあるスキャナ的なことできるツールある？ | find | `references/tools.md`（OCR/PDF） | 言い換え（「OCR」を含まない） |
| Q09 | 卒業までに取る資格の計画 | find | `references/career-roadmap.md` | 直撃だが「資格」は work にも出る＝順位を見る |
| Q10 | 扶養で気にする年収ラインの、K の判定はどこ | find | `references/fuyou.md`（制度は tax/nenshu-kabe-seido.md で**別**＝正解に含めない） | 制度と本人判定の分離を検索が区別できるか。bench は `` ` `` で囲んだパスだけを正解として読む |
| Q11 | references のファイルは全部で何件？ | count | `v_by_bundle`（bundle='references'） | ビュー |
| Q12 | K が確認済み（verified）の記録は references に何件ある？ | count | `v_unverified` の補集合（bundle='references'） | ビュー |
| Q13 | 期限切れ（stale_after 超過）の記録はいくつ？ | count | `v_stale` | ビュー。bench 実行日に依存＝JSON に実行日を記録 |
| Q14 | type が Life Data のファイルは何件？ | count | `v_by_type` | ビュー |
| Q15 | 扶養の制度知識を references から別ファイルに分けたのはいつ？ | asof | `references/INDEX.md` 横断トピック「扶養・年収の壁（分離日付あり）」→ Fact `subject=扶養知識の置き場` | 有効期間の切り替わり |
| Q16 | キャリアの候補職種は、2026-08 より前の時点では何と書いてあった？ | asof | `references/work.md` §キャリア方針の履歴（Fact: 2026-08-11 に3候補を申告） | 「以前」を問う＝valid_to が閉じた行 |
| Q17 | 収益目標を決めたのはいつで、当時の3枠は？ | asof | `references/money.md` §収益目標（2026-07-26 決定） | recorded_at と valid_from の一致確認 |
| Q18 | 2026-09 時点で、営業（受託）の能動活動は動いていた？ | asof | `references/money.md` §収益目標 ＋ memory `team-kuroko-plan`（2026-08-24 停止） | 「停止」という状態変化を時点で答える |
| Q19 | 生活の「効率化」方針は、全体としてどのファイルにどう反映されてる？ | overview | INDEX 横断トピック「効率化・最適化（北極星）」→ profile / home / money / tools の要約 | バンドル要約＋リンク |
| Q20 | K の健康まわりの記録、全体として何が手厚くて何が薄い？ | overview | `references/health.md` 全節＋INDEX「空欄・未着手」 | 要約階層（document → section）で答える |

## 運用
- 型ラベルは K の確認前は `draft`。K が一度眺めて OK を出したら `verified` を付ける
- 20問は固定しない。研究中に「型判定が割れた質問」を見つけたら**追加**する（削除しない。番号は増やすだけ）
- `expected` の所在が変わったら（ファイル分離など）、この表を直し `docs/log.md` に1行
