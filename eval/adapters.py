"""Adapter boundary: no gold SQL, answers, split, or rubric enters the agent."""

from dataclasses import dataclass

from contracts import FinalAnswer


@dataclass(frozen=True)
class PublicCase:
    question: str
    answer_type: str
    required_facts: tuple[str, ...]
    setup_turns: tuple[str, ...]
    new_session: bool
    user_id: str
    setup_task_id: str | None
    task_id: str


def public_case(question, user_id, setup_task_id, task_id):
    return PublicCase(question["question"], question["answer_type"], tuple(question.get("required_facts", [])),
        tuple(question.get("setup_turns", [])), question.get("new_session", False), str(user_id),
        str(setup_task_id) if setup_task_id else None, str(task_id))


class ZeroAdapter:
    name = "zero"
    version = "zero-v1"

    def run(self, case, emit):
        # The fixture deliberately returns 0 for EVERY question, even list/D cases.
        # No oracle SQL, model request or query result is created by this adapter.
        if case.new_session:
            emit("fixture_session", {"phase": "preference_setup", "task_id": case.setup_task_id,
                                     "turns": list(case.setup_turns)}, 0, 0)
            emit("fixture_session", {"phase": "new_session", "task_id": case.task_id}, 0, 0)
        return FinalAnswer(answer=0, claims=[{"text": "答案为 0", "value": 0, "evidence": []}])


def make_adapter(name):
    if name != "zero":
        raise ValueError("Only the zero fixture is implemented in Step 1; runtime agents start in Step 2")
    return ZeroAdapter()
