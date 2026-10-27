"""Unified registry for MCP and local tools; no database access."""

import json
from dataclasses import dataclass
from time import perf_counter

from contracts import FinalAnswer
from uuid import UUID
from agent.call_context import TOOL_CALL_ID

FINDING_TOOL = {"type":"function","function":{"name":"save_finding",
    "description":"Pin a key finding and its SQL result IDs outside compressible history. Notes are unverified until review.",
    "parameters":{"type":"object","properties":{"text":{"type":"string","maxLength":2000},
    "evidence":{"type":"array","items":{"type":"string"},"maxItems":10}},"required":["text","evidence"],"additionalProperties":False}}}

FINAL_TOOL = {"type":"function", "function":{"name":"final_answer",
    "description":'Submit the final answer with claims citing real result_id values. All business numbers must be computed by SQL, including counts, ratios and differences. For claims spanning multiple rows, value MUST be an array of row objects: each key is a SQL column name and each object comes from ONE result row. Format-only example: [{"customer_state":"SP","gmv":123.45},{"customer_state":"RJ","gmv":67.89}]. Never turn cell values into object keys or count returned rows yourself.',
    "parameters":{"type":"object", "properties":{
        "answer":{"description":"A number for numeric questions, an array for lists, or a report string."},
        "claims":{"type":"array", "items":{"type":"object", "properties":{
            "text":{"type":"string"}, "value":{"description":"Exact signed SQL value, one row object keyed by SQL column names, or an array of such row objects. Each object must match a single SQL result row."},
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
        self.notes = []
        self.definitions = [*remote.tools, FINAL_TOOL, FINDING_TOOL]
        self.handlers = {}
        for tool in remote.tools:
            name = tool["function"]["name"]
            if name in {"final_answer","save_finding"} or name in self.handlers:
                raise ValueError("Duplicate or reserved MCP tool name")
            async def call(arguments, tool_name=name):
                return ToolResult(await remote.call(tool_name, arguments))
            self.handlers[name] = call
        self.handlers["final_answer"] = self.finish
        self.handlers["save_finding"] = self.save_finding

    async def save_finding(self, arguments):
        text, evidence = arguments["text"], arguments["evidence"]
        if not isinstance(text,str) or not text.strip() or len(text)>2000 or not isinstance(evidence,list) or not 1<=len(evidence)<=10 or len(self.notes)>=20:
            raise ValueError("Finding needs bounded text and evidence; at most 20 notes")
        note = {"text":text,"evidence":[str(UUID(e)) for e in evidence]}
        self.notes.append(note)
        self.emit("finding",note)
        return ToolResult({"saved":True,"note_id":len(self.notes)})

    async def finish(self, arguments):
        answer = FinalAnswer.model_validate(arguments)
        return ToolResult({"accepted":True}, answer)

    async def _call(self, name, arguments, call_id, phase="agent"):
        start = perf_counter()
        self.emit("tool_call", {"name":name, "call_id":call_id, "phase":phase,
                               "input_summary":arguments[:2000] if isinstance(arguments, str) else arguments})
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            if name not in self.handlers:
                raise ValueError("Unknown tool")
            token = TOOL_CALL_ID.set(call_id)
            try:
                result = await self.handlers[name](args)
            finally:
                TOOL_CALL_ID.reset(token)
        except Exception as exc:
            result = ToolResult({"error":type(exc).__name__, "detail":str(exc)[:1500]})
        self.emit("tool_result", {"name":name, "call_id":call_id, "phase":phase,
            "output_summary":json.dumps(result.content, ensure_ascii=False)[:2000],
            "error":result.content.get("error"), "result_id":result.content.get("result_id")},
            0, (perf_counter()-start)*1000)
        return result


    async def call(self,name,arguments,call_id,phase="agent"):
        import telemetry
        with telemetry.span('execute_tool '+name,'agent',attributes={
                'gen_ai.operation.name':'execute_tool','gen_ai.tool.name':name}) as current:
            result=await self._call(name,arguments,call_id,phase)
            current.set_attributes(telemetry.tool_attributes(result.content))
            return result
