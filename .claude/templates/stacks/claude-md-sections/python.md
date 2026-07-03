## 技術スタック

- 開発環境: devcontainer
- Python 3.12+
- パッケージ管理: uv
- Lint + Format: ruff
- 型チェック: mypy (strict)
- テストフレームワーク: pytest (+ pytest-cov)

## 主要コマンド

```bash
uv sync               # 依存関係を解決・インストール
uv run ruff check .   # Lint
uv run ruff format .  # Format
uv run mypy src       # 型チェック
uv run pytest         # テスト実行 (カバレッジ込み)
```
