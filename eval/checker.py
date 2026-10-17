"""Independent evidence verification. Never imports an Agent or runtime Reviewer."""

import json
import re
from decimal import Decimal, InvalidOperation
from uuid import UUID

from contracts import FinalAnswer


def number(value):
    if isinstance(value, (bool, type(None), list, dict)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def equal(actual, expected, tolerance=Decimal("0.000001")):
    a, b = number(actual), number(expected)
    if a is not None and b is not None:
        return abs(a-b) <= max(abs(b)*tolerance, Decimal("0.00000001"))
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def supports(value, rows):
    if isinstance(value, dict):
        # Bind labels to values within ONE row; don't assemble an invented row
        # out of unrelated cells from different groups or columns.
        return bool(value) and any(all(k in row and equal(v, row[k]) for k,v in value.items()) for row in rows)
    if isinstance(value, list):
        return all(supports(v, rows) for v in value) if value else not rows
    return any(equal(value, cell) for row in rows for cell in row.values())


def numeric_leaves(value):
    if isinstance(value, dict):
        return [n for v in value.values() for n in numeric_leaves(v)]
    if isinstance(value, list):
        return [n for v in value for n in numeric_leaves(v)]
    n = number(value)
    return [] if n is None else [n]


def report_numbers(text):
    # Dates, quarter labels and list numbering are context, not measured facts.
    text = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "", text)
    text = re.sub(r"\b\d{4}\s*[-年]?\s*Q[1-4]\b|\b\d{4}-\d{2}(?:-\d{2})?\b|\d{4}\s*年|\bQ[1-4]\b", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)、]\s*", "", text)
    pattern = r"(?<![A-Za-z0-9_])([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?)(?![A-Za-z0-9_])\s*(万|亿|千)?"
    scale = {None: 1, "千": 1000, "万": 10000, "亿": 100000000}
    return [Decimal(m[1].replace(",", ""))*scale[m[2]] for m in re.finditer(pattern, text)]


class DatabaseEvidence:
    def __init__(self, connection):
        self.connection = connection

    def __call__(self, result_ids):
        if not result_ids:
            return {}
        rows = self.connection.execute(
            "SELECT result_id, task_id, data_version, rows FROM query_results WHERE result_id = ANY(%s)",
            ([UUID(value) for value in result_ids],)).fetchall()
        return {str(row[0]): {"task_id": str(row[1]), "data_version": row[2], "rows": row[3]} for row in rows}


def check(response: FinalAnswer, fetch, task_id: str, data_version: str):
    ids = sorted({ref for claim in response.claims for ref in claim.evidence})
    stored = fetch(ids)
    outcomes, grounded_numbers = [], []
    for claim in response.claims:
        valid = bool(claim.evidence)
        rows = []
        reason = "no_evidence" if not valid else "value_not_in_result"
        for reference in claim.evidence:
            evidence = stored.get(reference)
            if evidence is None:
                valid, reason = False, "missing_result"
            elif evidence["task_id"] != str(task_id):
                valid, reason = False, "wrong_task"
            elif evidence["data_version"] != data_version:
                valid, reason = False, "stale_data_version"
            else:
                rows.extend(evidence["rows"])
        supported = valid and supports(claim.value, rows)
        outcomes.append({"supported": supported, "reason": None if supported else reason})
        if supported:
            grounded_numbers.extend(numeric_leaves(claim.value))
    texts = [response.answer if isinstance(response.answer, str) else json.dumps(response.answer, ensure_ascii=False)]
    texts.extend(claim.text for claim in response.claims)
    measured = [n for text in texts for n in report_numbers(text)]
    # Prose may say "下降 5%" for SQL's -5. Claims retain the signed SQL value;
    # only the report's numeric surface form is matched by magnitude.
    unsupported_numbers = sum(not any(equal(abs(n), abs(source), Decimal("0.01"))
                                     for source in grounded_numbers) for n in measured)
    unsupported_claims = sum(not item["supported"] for item in outcomes)
    return {"claims": outcomes, "claim_count": len(outcomes), "unsupported_claims": unsupported_claims,
        "unsupported_claim_ratio": unsupported_claims/len(outcomes) if outcomes else None,
        "report_number_count": len(measured), "unsupported_numbers": unsupported_numbers,
        "unsupported_number_ratio": unsupported_numbers/len(measured) if measured else None}
