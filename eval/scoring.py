"""Gold-answer correctness is separate from evidence support."""

import json
from decimal import Decimal

from eval.checker import equal, number


def gold_answer(question, rows):
    kind = question["answer_type"]
    if kind == "number":
        if len(rows) != 1 or len(rows[0]) != 1 or number(next(iter(rows[0].values()))) is None:
            raise ValueError("Number oracle must return one finite numeric cell")
        return next(iter(rows[0].values()))
    if kind == "list":
        return [next(iter(row.values())) if len(row) == 1 else row for row in rows]
    if len(rows) != 1 or set(rows[0]) != set(question["required_facts"]):
        raise ValueError("Key-fact oracle must return one row with exactly the required fact keys")
    if any(value is None for value in rows[0].values()):
        raise ValueError("Required gold facts cannot be NULL")
    return rows[0]


def canonical(value):
    if isinstance(value, dict):
        return tuple(sorted((k, canonical(v)) for k,v in value.items()))
    if isinstance(value, list):
        return tuple(canonical(v) for v in value)
    if isinstance(value, bool):
        return ("bool", value)
    numeric = number(value)
    return ("number", numeric) if numeric is not None else ("value", json.dumps(value, sort_keys=True))


def score(question, response, gold, evidence):
    kind = question["answer_type"]
    hit, total = None, None
    if kind == "number":
        correct = number(response.answer) is not None and equal(response.answer, gold, Decimal("0.01"))
    elif kind == "list":
        correct = isinstance(response.answer, list) and {canonical(v) for v in response.answer} == {canonical(v) for v in gold}
    else:
        total, hit = len(gold), 0
        for key, expected in gold.items():
            candidates = [claim.value[key] for claim in response.claims if isinstance(claim.value, dict) and key in claim.value]
            # Contradictory duplicate claims do not earn fact credit.
            hit += bool(candidates) and all(equal(v, expected, Decimal("0.01")) for v in candidates)
        correct = (isinstance(response.answer, str) and bool(response.answer.strip())
            and hit == total and evidence["claim_count"] > 0
            and evidence["unsupported_claims"] == 0 and evidence["unsupported_numbers"] == 0)
    return {"correct": bool(correct), "fact_hits": hit, "fact_total": total,
            "fact_hit_rate": hit/total if total else None}
