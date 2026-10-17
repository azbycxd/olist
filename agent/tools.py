"""Unified registry for MCP and local tools; no database access."""

import json
from dataclasses import dataclass
from time import perf_counter

from contracts import FinalAnswer

FINAL_TOOL = {"type":"function", "function":{"name":"final_answer",
    "description":"Submit the final answer with claims citing real result_id values. All business numbers must be computed by SQL, including ratios and differences.",
    "parameters":{"type":"object", "properties":{
        "answer":{"description":"A number for numeric questions, an array for lists, or a report string."},
        "claims":{"type":"array", "items":{"type":"object", "properties":{
            "text":{"type":"string"}, "value":{"description":"Exact signed SQL value or an object binding SQL column names to values."},
            "evidence":{"type":"array", "items":{"type":"string"}}},
            "required":["text","value","evidence"], "additionalProperties":False}}},
        "required":["answer","claims"], "additionalProperties":False}}}


def untrusted(value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e")
    return "<untrusted_tool_result>\n"+payload+"\n</untrusted_tool_result>"


@dataclass
class ToolResult:
    content: dict
    final: FinalAnswer | None = None


class Registry:
    def __init__(self, remote, emit):
        self.emit = emit
        self.definitions = [*remote.tools, FINAL_TOOL]
        self.handlers = {}
        for tool in remote.tools:
            name = tool["function"]["name"]
            if name == "final_answer" or name in self.handlers:
                raise ValueError("Duplicate or reserved MCP tool name")
            async def call(arguments, tool_name=name):
                return ToolResult(await remote.call(tool_name, arguments))
            self.handlers[name] = call
        self.handlers["final_answer"] = self.finish

    async def finish(self, arguments):
        answer = FinalAnswer.model_validate(arguments)
        return ToolResult({"accepted":True}, answer)

    async def call(self, name, arguments, call_id, phase="agent"):
        start = perf_counter()
        self.emit("tool_call", {"name":name, "call_id":call_id, "phase":phase,
                               "input_summary":arguments[:2000] if isinstance(arguments, str) else arguments})
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            if name not in self.handlers:
                raise ValueError("Unknown tool")
            result = await self.handlers[name](args)
        except Exception as exc:
            result = ToolResult({"error":type(exc).__name__, "detail":str(exc)[:1500]})
        self.emit("tool_result", {"name":name, "call_id":call_id, "phase":phase,
            "output_summary":json.dumps(result.content, ensure_ascii=False)[:2000],
            "error":result.content.get("error"), "result_id":result.content.get("result_id")},
            0, (perf_counter()-start)*1000)
        return result
