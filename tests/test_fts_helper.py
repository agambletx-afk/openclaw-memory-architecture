import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fts_helper import build_or_match_query, tokenize_for_fts


def test_tokenize_strips_operator_syntax_chars():
    tokens = tokenize_for_fts('NOT NEAR AND OR "quoted" a* (grouped)', min_len=1)
    assert tokens == ["not", "near", "and", "or", "quoted", "a", "grouped"]


def test_build_or_match_query_escapes_operator_like_words():
    query = build_or_match_query('NOT NEAR AND OR')
    assert query == '"not" OR "near" OR "and" OR "or"'


def test_build_or_match_query_escapes_quotes_and_special_chars():
    query = build_or_match_query('"double quotes" foo* (bar)')
    assert query == '"double" OR "quotes" OR "foo" OR "bar"'


def test_escaped_query_executes_without_fts_syntax_errors():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(content)")
    db.executemany(
        "INSERT INTO docs(content) VALUES (?)",
        [
            ("operator words not near and or",),
            ("contains double quotes and parenthesis",),
            ("foo bar baz",),
        ],
    )

    for user_input in [
        "NOT",
        "NEAR",
        "AND",
        "OR",
        '"double quotes"',
        "foo*",
        "(bar)",
    ]:
        match_expr = build_or_match_query(user_input)
        rows = db.execute("SELECT content FROM docs WHERE docs MATCH ?", (match_expr,)).fetchall()
        assert isinstance(rows, list)
