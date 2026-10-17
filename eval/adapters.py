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
    if name == "zero":
        return ZeroAdapter()
    if name == "single":
        return SingleAdapter()
    raise ValueError("Unknown adapter")


class SingleAdapter:
    name = "single"
    version = "single-v1"

    def __init__(self):
        import os
        if not all(os.getenv(k) for k in ("OPENAI_API_KEY","OPENAI_MODEL","MCP_BEARER_TOKEN")):
            raise ValueError("Configure OPENAI_API_KEY, OPENAI_MODEL and MCP_BEARER_TOKEN before evaluating")

    def run(self, case, emit):
        from scripts.runtime import run_runtime
        if case.setup_turns:
            emit('preference_session',{'phase':'setup','task_id':case.setup_task_id})
            run_runtime('\n'.join(case.setup_turns),case.setup_task_id,emit,preference_only=True)
            emit('preference_session',{'phase':'new_session','task_id':case.task_id})
        # Pass only public question fields into the isolated model process.
        question = case.question+"\n输出类型："+case.answer_type
        if case.required_facts:
            question += "；报告需要的事实字段："+", ".join(case.required_facts)
        return run_runtime(question, case.task_id, emit,user_text=case.question)
