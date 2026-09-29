"""`dbr facts`: 取り込み済み断片から「いつからの事実か」を機械抽出して fact 表へ.

抽出元は 3 種:
- explicit   : フロントマターの独自キー `valid: { from, to }`（文書全体の事実）
- dated_text : 見出し・本文の行にある `YYYY-MM-DD ＋ 動詞`（K申告／K決定／分離 …）
- inferred   : どちらも無い文書は `generated_at` を暫定の valid_from にする
               （回答では「暫定」と明示）
bundle 単位で全削除→再挿入するので、同じ入力なら同じ行になる（決定的）。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from dbr.features.ingest.frontmatter import JST, to_datetime
from dbr.shared.db import connect
from dbr.shared.text import lexemes

VERBS = (
    "K申告|K承認|K決定|K指示|決定|承認|分離|申告|記録|算出|"
    "停止|廃止|変更|開始|導入|確定|更新"
)
# 日付と動詞の間に短い目的語が入る形（「2026-08-24 A枠の能動営業停止」）も拾う。
# 窓は同一行内 20 字まで（行をまたがない・遠い動詞を拾わない）。窓の中に**次の日付が
# 現れたら打ち切る**（「2026-08-01 に検討、2026-08-11 決定」を 08-01 の決定と
# 読まないため。受入検証 D3・2026-09-29）
_WINDOW = r"(?:(?!20\d{2}-\d{2}-\d{2})[^\n]){0,20}?"
DATE_VERB = re.compile(rf"(20\d{{2}})-(\d{{2}})-(\d{{2}}){_WINDOW}({VERBS})")
DATE_ANY = re.compile(r"20\d{2}-\d{2}-\d{2}")
SUBJECT_HEAD = 40
VALUE_MAX = 300


@dataclass(frozen=True)
class FactRow:
    document_id: int
    chunk_id: int | None
    subject: str
    value: str
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    valid_source: str


@dataclass
class FactsReport:
    bundle: str
    explicit: int = 0
    dated_text: int = 0
    inferred: int = 0
    skipped_no_date: int = 0  # generated_at も無く暫定すら置けない文書

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def parse_ymd(y: str, m: str, d: str) -> datetime | None:
    try:
        return datetime(int(y), int(m), int(d), tzinfo=JST)
    except ValueError:
        return None  # 2026-13-40 のような不正日付は無視


def normalize_subject(heading: str, line: str) -> str:
    """直近見出し ＋ 行頭 40 字（日付と動詞を除く・NFKC・空白圧縮）."""
    head = DATE_VERB.sub("", line)
    head = DATE_ANY.sub("", head)
    head = unicodedata.normalize("NFKC", head)
    head = re.sub(r"[\s（）()「」『』*_`#|>-]+", " ", head).strip()[:SUBJECT_HEAD]
    last = heading.split(" > ")[-1] if heading else ""
    last = unicodedata.normalize("NFKC", DATE_VERB.sub("", last)).strip()
    return f"{last} / {head}".strip(" /") or "(無題)"


def extract_dated(
    *,
    document_id: int,
    chunk_id: int,
    heading_path: str,
    body: str,
    recorded_at: datetime,
) -> list[FactRow]:
    """見出し行＋本文の各行から日付つきの事実を抽出（同じ行・同じ日付は 1 件）.

    重複判定は（日付, 行）で行う。subject で畳むと、見出しが同じで日付＋動詞しか
    違わない別々の行（「- 2026-08-11 決定」「- 2026-08-11 承認」）が 1 件に消える
    （受入検証 D3・実データで 2 行）。
    """
    last_heading = heading_path.split(" > ")[-1] if heading_path else ""
    lines = ([last_heading] if last_heading else []) + body.split("\n")
    seen: dict[tuple[datetime, str], FactRow] = {}
    for line in lines:
        for m in DATE_VERB.finditer(line):
            when = parse_ymd(m.group(1), m.group(2), m.group(3))
            if when is None:
                continue
            value = line.strip()[:VALUE_MAX]
            key = (when, value)
            if key in seen:
                continue
            seen[key] = FactRow(
                document_id=document_id,
                chunk_id=chunk_id,
                subject=normalize_subject(heading_path, line),
                value=value,
                valid_from=when,
                valid_to=None,
                recorded_at=recorded_at,
                valid_source="dated_text",
            )
    return list(seen.values())


def _exclusive_end(raw: object) -> datetime | None:
    """`valid.to` を排他的な終端に直す。日付だけならその日を**含む**ので翌日 0 時.

    as_of は `at < valid_to` で判定するので、日付を 0 時のままにすると最終日が
    有効期間から外れる（受入検証・任意 2026-09-29）。時刻つきの値はそのまま。
    """
    end = to_datetime(raw)
    if end is None:
        return None
    date_only = (isinstance(raw, date) and not isinstance(raw, datetime)) or (
        isinstance(raw, str) and len(raw.strip()) == 10
    )
    return end + timedelta(days=1) if date_only else end


def extract_explicit(
    *, document_id: int, fm: dict[str, Any], title: str, recorded_at: datetime
) -> FactRow | None:
    valid = fm.get("valid")
    if not isinstance(valid, dict):
        return None
    start = to_datetime(valid.get("from"))
    if start is None:
        return None
    end = _exclusive_end(valid.get("to"))
    if end is not None and end <= start:
        end = None
    desc = fm.get("description")
    return FactRow(
        document_id=document_id,
        chunk_id=None,
        subject=str(desc) if desc else title,
        value=str(desc) if desc else title,
        valid_from=start,
        valid_to=end,
        recorded_at=recorded_at,
        valid_source="explicit",
    )


def run_facts(bundle: str, dsn: str) -> FactsReport:
    report = FactsReport(bundle=bundle)
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, rel_path, fm, generated_at, ingested_at FROM document "
            "WHERE bundle = %(b)s ORDER BY id",
            {"b": bundle},
        )
        docs = cur.fetchall()
        cur.execute(
            "DELETE FROM fact WHERE document_id IN "
            "(SELECT id FROM document WHERE bundle = %(b)s)",
            {"b": bundle},
        )
        rows: list[FactRow] = []
        for d in docs:
            doc_id = int(str(d["id"]))
            fm = d["fm"] if isinstance(d["fm"], dict) else {}
            gen = d["generated_at"]
            recorded = gen if isinstance(gen, datetime) else d["ingested_at"]
            assert isinstance(recorded, datetime)
            cur.execute(
                "SELECT id, heading_path, body FROM chunk "
                "WHERE document_id = %(d)s ORDER BY ordinal",
                {"d": doc_id},
            )
            chunks = cur.fetchall()
            doc_rows: list[FactRow] = []
            ex = extract_explicit(
                document_id=doc_id,
                fm=fm,
                title=str(d["rel_path"]),
                recorded_at=recorded,
            )
            if ex:
                doc_rows.append(ex)
                report.explicit += 1
            for c in chunks:
                found = extract_dated(
                    document_id=doc_id,
                    chunk_id=int(str(c["id"])),
                    heading_path=str(c["heading_path"]),
                    body=str(c["body"]),
                    recorded_at=recorded,
                )
                doc_rows.extend(found)
                report.dated_text += len(found)
            if not doc_rows:
                if isinstance(gen, datetime):
                    desc = fm.get("description")
                    doc_rows.append(
                        FactRow(
                            document_id=doc_id,
                            chunk_id=None,
                            subject=str(desc) if desc else str(d["rel_path"]),
                            value=str(desc) if desc else str(d["rel_path"]),
                            valid_from=gen,
                            valid_to=None,
                            recorded_at=gen,
                            valid_source="inferred",
                        )
                    )
                    report.inferred += 1
                else:
                    report.skipped_no_date += 1
            rows.extend(doc_rows)
        with cur.copy(
            "COPY fact (document_id, chunk_id, subject, value, valid_from, valid_to, "
            "recorded_at, valid_source, lexemes) FROM STDIN"
        ) as copy:
            for r in rows:
                copy.write_row(
                    (
                        r.document_id,
                        r.chunk_id,
                        r.subject,
                        r.value,
                        r.valid_from,
                        r.valid_to,
                        r.recorded_at,
                        r.valid_source,
                        lexemes(f"{r.subject}\n{r.value}"),
                    )
                )
    return report
