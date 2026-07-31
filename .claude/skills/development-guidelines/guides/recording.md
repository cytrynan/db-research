# ドキュメント記録規約（OKF準拠）

出典: Google Cloud の Open Knowledge Format v0.2
（https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md）。
OKFから3点を採用する: **①フロントマターによる鮮度・信頼の明示 ②log.md による変更履歴 ③アクター規約**。

## なぜ必要か

エージェントがドキュメントを書き続けるプロジェクトでは、次の3つが本文からは判定できなくなる:

1. **誰が書いたか** — 人間の設計判断か、エージェントの生成物か
2. **確認済みか** — ユーザーがレビューして承認した内容か、生成されただけの内容か
3. **まだ正しいか** — 書かれた時点では正しかった記述が、今も有効か

これらを散文の注記（「2026-07-28 承認」等）でなくフロントマターで機械可読にするのがこの規約。
散文注記は人間可読として併用してよいが、**機械可読の正はフロントマター**。

## 適用対象

- **必須**: `docs/` の恒久ドキュメント（PRD・機能設計・アーキテクチャ等の6ドキュメント、`DESIGN.md`）
- **任意**: `.steering/` の作業ドキュメント（短命なので費用対効果で判断）、`docs/ideas/` の下書き
- **移行**: 既存ドキュメントは**内容を触ったついでに付与**する（遡及一括変換はしない）

## ①フロントマター仕様

```yaml
---
type: Functional Design            # 必須。ドキュメントの種類（PRD / Functional Design / Architecture /
                                   # Repository Structure / Development Guidelines / Glossary / Design Tokens 等）
generated: { by: claude/<モデルID>, at: 2026-08-01T03:00:00+09:00 }  # 内容を最後に書いた者。更新のたびに書き換える
verified: { by: human:<ユーザーID>, at: 2026-08-01T03:30:00+09:00 }   # 内容の正しさを確認した者。未確認なら書かない
stale_after: 2026-12-31            # 任意。腐る知識のみ（外部APIのバージョン・料金・依存の前提等）。絶対日付
status: stable                     # 省略=stable。レビュー前=draft。廃止=削除せず deprecated
---
```

運用ルール:

- **generated と verified は別物**（書いた者≠確認した者）。エージェントが書いてユーザー未確認なら `verified` を付けない。ドキュメント承認フロー（「承認いただけたら次へ」）で承認を得た時点で `verified: { by: human:<ユーザーID>, at }` を付ける
- **内容を実質的に変えたら、古い `verified` は外す**（「確認済み」表示が嘘になるため）。再承認されたら付け直す
- `stale_after` は全部に付けない。腐らない記述（設計原則・用語定義）には不要。超過を見つけたら再確認してから使う
- 廃止したドキュメント・節は削除でなく `status: deprecated`（リンクと履歴のために残す）
- 未知のフロントマターキーがあっても拒否しない（OKFの寛容原則）

## ②docs/log.md（変更履歴）

`docs/` 配下のドキュメントを作成・更新・廃止したら、**同じ作業内で** `docs/log.md` に1行追記する。
形式（新しい順・日付見出しは ISO 8601）:

```markdown
## 2026-08-01
* **Update**: [機能設計書](functional-design.md) — 認証フローにOAuth対応を追記 (claude/<モデルID>)
* **Creation**: [用語集](glossary.md) — 初版作成 (claude/<モデルID>)
```

- 先頭の太字は **Creation / Update / Deprecation** の3種
- 「なぜ変えたか」が一言で書けるなら添える
- git履歴の代替ではない: log.md は「人間が週次で読める粒度の要約」、git は行単位の証跡。両方持つ

## ③アクター規約

| 種別 | 表記 | 例 |
|---|---|---|
| 人間 | `human:<id>` | `human:alice` |
| エージェント | `<producer>/<モデルID>` | `claude/claude-sonnet-5` |
| 自動プロセス | `process:<id>` | `process:ci-docs-sync` |

信頼の3段階判定（`verified` から機械的に導出）:

1. `verified` なし → **unverified**（生成されただけ。裏取りなし）
2. `verified` が機械アクターのみ → **machine-confirmed**（自動チェックは通った）
3. `verified` に `human:` あり → **human-reviewed**（人間承認済み）

「承認されたドキュメントだけを実装の根拠にする」「未承認ドキュメントの一覧を出す」等の判定は、
この3段階を使って `verified` の有無と `human:` プレフィックスだけで行う。
