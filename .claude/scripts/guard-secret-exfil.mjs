#!/usr/bin/env node
// guard-secret-exfil.mjs — PreToolUse(Bash) フック
//
// 責務（1つだけ）: 機密ファイルが外部へ出る Bash コマンドを機械的に止める。
//
// なぜ「規約に書く」でなく「機構で止める」か:
//   規範文言による防御は、規範が**想起されること**に依存する。実測（対照実験・540走行）では、
//   禁止条項を破った走行の 94% で、その条項に一度も言及されていなかった。
//   つまり文言を足しても、想起されない場面では効かない。フックは想起に依存しない。
//
// 設計規律:
//   ①1フック=1責務  ②PreToolUse なので軽い正規表現照合のみ・ファイルI/Oなし
//   ③故障注入テスト（tests/test-guard-secret-exfil.mjs）とセットで運用する
//   ④フック台帳（docs/ もしくは CLAUDE.md）を同じ作業内で更新する
//
// 契約: stdin にイベントJSON / exit 0 + stdout JSON（deny のときだけ出力。通常は沈黙）
// フェイルオープン: 入力が壊れても例外が出ても必ず exit 0。
//   フックの誤作動で日常の作業が止まる方が、稀な流出より高くつく。
//
// 設定: 環境変数 GUARD_SECRET_PATTERNS にカンマ区切りの追加パターンを渡せる。
//   例: GUARD_SECRET_PATTERNS="customer-data/,*.pfx"

import fs from 'node:fs';

// 既定の機密パターン。プロジェクトに合わせて増やす。
const DEFAULT_SECRETS = [
  '\\.env(\\.|$|["\'\\s;&|)])',
  'secrets?[\\/\\\\]',
  'credentials?[\\.\\/\\\\]',
  '\\.pem\\b',
  '\\.p12\\b',
  'id_rsa\\b',
  'service-account.*\\.json',
];

function secretRegex() {
  const extra = (process.env.GUARD_SECRET_PATTERNS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp([...DEFAULT_SECRETS, ...extra].join('|'), 'i');
}

const NET_VERB =
  /(^|[\s;&|(])(curl|wget|scp|rsync|sftp|ftp|nc|ncat|telnet|Invoke-WebRequest|Invoke-RestMethod|iwr|mail|sendmail)([\s;&|)]|$)/i;

// `git push` / `git -C <dir> push` / `git --git-dir=... push`
// ★罠: `git(\s+-\S+)*\s+push` と書くと `-C <dir>` のように「値を別トークンで取る」
//   オプションを挟んだ形を拾えず、素通しになる。故障注入で発見した実例。
const GIT_PUSH = /(^|[\s;&|(])git\b[^;&|]*?\s+push([\s;&|)]|$)/i;
const GH_PUBLISH = /(^|[\s;&|(])gh\s+(gist\s+create|repo\s+create)/i;

export function decide(command) {
  const cmd = String(command || '');
  if (!cmd) return null;
  const SECRET = secretRegex();
  if (!SECRET.test(cmd)) return null;

  if (GIT_PUSH.test(cmd)) {
    return '機密ファイルを含む push を検出した。public / private を問わず外部ホスティングへ出さない。';
  }
  if (GH_PUBLISH.test(cmd)) {
    return '機密ファイルを gist / 新規リポジトリとして公開しない。';
  }
  if (NET_VERB.test(cmd)) {
    return '機密ファイルの内容を外部へ送信しない。';
  }
  return null;
}

function main() {
  let input;
  try {
    input = JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    process.exit(0);
  }
  if (input.hook_event_name && input.hook_event_name !== 'PreToolUse') process.exit(0);
  if (input.tool_name && input.tool_name !== 'Bash') process.exit(0);

  const reason = decide(input?.tool_input?.command);
  if (!reason) process.exit(0);

  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason:
        reason + '\nこの判断は会話上の指示では覆らない（機構による遮断）。'
        + '\n本当に必要なら、このフックの設定を変更する提案を人間に出して承認を得ること。',
    },
  }));
  process.exit(0);
}

if (process.argv[1] && process.argv[1].endsWith('guard-secret-exfil.mjs')) {
  try {
    main();
  } catch (e) {
    process.stdout.write(JSON.stringify({
      systemMessage: `⚠ guard-secret-exfil フック自体がエラー: ${e?.message ?? e}`,
    }));
    process.exit(0);
  }
}
