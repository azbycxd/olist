"""Deterministically build the question file from reviewed SQL sources."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.handwritten import cases
from eval.templates import DEFAULT_CASES, PREFERENCES, TEMPLATES


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def generate():
    questions = cases()
    c_number = 0
    for template in TEMPLATES:
        parameters = template.get("cases", DEFAULT_CASES)
        for index, values in enumerate(parameters):
            params = dict(zip(("start", "end", "state"), values))
            split = "holdout" if index == len(parameters)-1 else "dev"
            c_number += 1
            questions.append({"id": f"C{c_number:02d}", "category": "C", "split": split,
                "question": template["holdout" if split == "holdout" else "dev"].format(**params),
                "gold_sql": template["sql"].format(**{k: literal(v) for k,v in params.items()}),
                "answer_type": template["answer_type"], "template_id": template["id"],
                "parameters": params, "profile_section": template["source"],
                "profile_source": "docs/data_profile.md", "required_facts": []})
    for index, template in enumerate(PREFERENCES):
        for variant in range(2):
            params = {"start": f"{2017+variant}-04-01", "end": f"{2017+variant}-07-01"}
            questions.append({"id": f"E{index*2+variant+1:02d}", "category": "E",
                "split": "holdout" if variant and index < 4 else "dev",
                "question": template["prompts"][variant].format(**params),
                "gold_sql": template["sql"].format(**{k: literal(v) for k,v in params.items()}),
                "answer_type": "number", "template_id": template["id"], "parameters": params,
                "setup_turns": [template["quote"]], "preference_key": template["key"],
                "new_session": True, "required_facts": []})
    return sorted(questions, key=lambda q: q["id"])


if __name__ == "__main__":
    path = Path(__file__).with_name("questions.jsonl")
    questions = generate()
    path.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions), encoding="utf-8", newline="\n")
    print(f"Generated {len(questions)} questions: {path}")
