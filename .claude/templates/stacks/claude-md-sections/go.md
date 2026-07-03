## 技術スタック

- 開発環境: devcontainer
- Go 1.22+
- Lint: golangci-lint
- テスト: 標準 `testing` パッケージ

## 主要コマンド

```bash
go build ./...        # ビルド
go vet ./...          # 静的解析
gofmt -l .            # フォーマット差分の表示
golangci-lint run     # Lint
go test ./... -cover  # テスト実行 (カバレッジ込み)
```
