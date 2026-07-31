---
name: development-guidelines
description: チーム全体で統一された開発プロセスとコーディング規約を確立するための包括的なガイドとテンプレート。開発ガイドライン作成時、コード実装時に使用する。
allowed-tools: Read, Write, Edit
---

# 開発ガイドラインスキル

チーム開発に必要な4つの要素をカバーします:
1. 実装時のコーディング規約 (guides/implementation.md)
2. 開発プロセスの標準化 (guides/process.md)
3. 検証の設計（外部連携・無人実行の証跡と完了判定）(guides/verification.md)
4. ドキュメント記録規約（OKF準拠のフロントマター・log.md・アクター規約）(guides/recording.md)

## 前提条件

開発ガイドライン作成を開始する前に、以下を確認してください:

### 推奨ドキュメント

1. `docs/architecture.md` (アーキテクチャ設計書) - 技術スタックの確認
2. `docs/repository-structure.md` (リポジトリ構造) - ディレクトリ構造の確認

開発ガイドラインは、プロジェクトの技術スタックとディレクトリ構造に
基づいた具体的なコーディング規約と開発プロセスを定義します。

## 既存ドキュメントの優先順位

**重要**: `docs/development-guidelines.md` に既存の開発ガイドラインがある場合、
以下の優先順位に従ってください:

1. **既存の開発ガイドライン (`docs/development-guidelines.md`)** - 最優先
   - プロジェクト固有の規約とプロセスが記載されている
   - このスキルのガイドより優先する

2. **このスキルのガイド** - 参考資料
   - ./guides/implementation.md: 汎用的なコーディング規約
   - ./guides/process.md: 汎用的な開発プロセス
   - ./guides/verification.md: 汎用的な検証設計（外部連携・無人実行）
   - 既存ガイドラインがない場合、または補足として使用

**新規作成時**: このスキルのガイドとテンプレートを参照
**更新時**: 既存ガイドラインの構造と内容を維持しながら更新

## 出力先

作成した開発ガイドラインは以下に保存してください:

```
docs/development-guidelines.md
```

## クイックリファレンス

### コード実装時
コード実装時のルールと規約: ./guides/implementation.md

含まれる内容:
- コーディング規約（言語共通の原則。コード例は TypeScript）
- 型定義・命名規則
- 関数設計とエラーハンドリング
- コメント規約
- セキュリティとパフォーマンス
- テストコード実装
- リファクタリング手法

### 開発プロセスの参照／策定時
Git運用、テスト戦略、コードレビュー: ./guides/process.md

含まれる内容:
- 基本原則（具体例の重要性、理由説明）
- Git運用ルール（Git Flow ブランチ戦略）
- コミットメッセージとPRプロセス
- テスト戦略（ピラミッドとカバレッジ）
- コードレビューのプロセス
- 品質自動化

### 外部連携・無人実行の検証設計時
証跡・ground truth・完了判定: ./guides/verification.md

含まれる内容:
- 検証は必ず証跡（`reports/*.json`）を残す。後始末は PASS 時だけ
- ground truth はサービス側に聞く（UIを信じない）／fail の名前を分ける
- 資格情報をスクリプトに持たせない（`--assist` 方式・待ち合わせファイル）
- 無人実行の完了判定（3条件のAND）と権限の前渡し

### ドキュメントの作成・更新時（`docs/` 恒久ドキュメント）
鮮度・信頼のフロントマターと変更履歴: ./guides/recording.md

含まれる内容:
- フロントマター仕様（`type` 必須・`generated`・`verified`・`stale_after`・`status`）
- `docs/log.md` への変更履歴の追記形式
- アクター規約（`human:<id>` / `<producer>/<モデルID>` / `process:<id>`）と信頼3段階の判定

### テンプレート
開発ガイドライン作成時: ./template.md


## 使用シーン別ガイド

### 新規開発時
1. ./guides/implementation.md で命名規則・コーディング規約を確認
2. ./guides/process.md でブランチ戦略・PR処理を確認
3. テストを先に書く（TDD）

### コードレビュー時
- ./guides/process.md の「コードレビュープロセス」を参照
- ./guides/implementation.md で規約違反がないか確認

### テスト設計時
- ./guides/process.md の「テスト戦略」（ピラミッド、カバレッジ）
- ./guides/implementation.md の「テストコード」（実装パターン）

### 外部サービス連携の実装・検証時
- ./guides/verification.md の原則1〜6（証跡・ground truth・fail の分離）
- UIの表示だけで成否を判定していないか確認

### `docs/` のドキュメントを作成・更新する時
- ./guides/recording.md のフロントマター仕様（承認を得たら `verified` を付け、実質変更したら外す）
- 同じ作業内で `docs/log.md` に1行追記

### リリース準備時
- ./guides/process.md の「Git運用ルール」（main へのマージ方針）
- コミットメッセージが Conventional Commits に従っているか確認

## チェックリスト

- [ ] コーディング規約が具体例付きで定義されている
- [ ] 命名規則が明確である（言語別・プロジェクト固有）
- [ ] エラーハンドリングの方針が定義されている
- [ ] ブランチ戦略が決まっている（Git Flow推奨）
- [ ] コミットメッセージ規約が明確である
- [ ] PRテンプレートが用意されている
- [ ] テストの種類とカバレッジ目標が設定されている
- [ ] コードレビュープロセスが定義されている
- [ ] CI/CDパイプラインが構築されている