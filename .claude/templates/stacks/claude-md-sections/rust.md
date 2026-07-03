## 技術スタック

- 開発環境: devcontainer
- Rust (edition 2021, stable)
- パッケージ管理: cargo
- Lint: clippy
- Format: rustfmt
- テスト: 標準 (`cargo test`)

## 主要コマンド

```bash
cargo build            # ビルド
cargo run              # 実行
cargo fmt --check      # フォーマットチェック
cargo clippy -- -D warnings  # Lint (warning も拒否)
cargo test             # テスト実行
```
