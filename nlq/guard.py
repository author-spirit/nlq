"""Reject anything that is not one SELECT statement. This is not a SQL parser."""

from __future__ import annotations

import re

QUESTION_MAX = 500

DENY_WORDS = (
    "attach",
    "copy",
    "install",
    "load",
    "pragma",
    "set",
    "call",
    "export",
    "read_csv",
    "read_parquet",
    "read_json",
    "glob",
)


class GuardError(Exception):
    pass


def check_question(question: str) -> str:
    text = question.strip()
    if not text:
        raise GuardError("Question is empty.")
    if len(text) > QUESTION_MAX:
        raise GuardError(f"Question is longer than {QUESTION_MAX} characters.")
    return text


def check_sql(sql: str) -> str:
    if sql is None or not str(sql).strip():
        raise GuardError("SQL is empty.")
    body = _one_statement(str(sql))
    checked = _strip_comments(body).strip()
    match = re.match(r"([A-Za-z]+)\b", checked)
    if match is None or match.group(1).upper() not in {"SELECT", "WITH"}:
        raise GuardError("Only a SELECT statement is allowed.")
    for word in DENY_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", checked, flags=re.IGNORECASE):
            raise GuardError(f"SQL contains a denied word: {word}")
    return body.strip()


def _one_statement(sql: str) -> str:
    semis: list[int] = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] == "'":
            i += 1
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = n if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if sql[i] == ";":
            semis.append(i)
        i += 1
    if not semis:
        return sql
    if len(semis) > 1 or sql[semis[0] + 1 :].strip():
        raise GuardError("Only one SQL statement is allowed.")
    return sql[: semis[0]]


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                    continue
                if sql[j] == "'":
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            continue
        if sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = n if newline < 0 else newline
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(sql[i])
        i += 1
    return "".join(out)
