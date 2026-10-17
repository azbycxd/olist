import asyncio
import os
from uuid import uuid4

import httpx
import psycopg
import pytest

from agent.mcp_client import MCPClient
from config import MCP_BEARER_TOKEN, MCP_URL, db_kwargs

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.getenv("RUN_MCP_TESTS") != "1", reason="requires the live MCP service")]


def test_live_protocol_authentication_results_and_errors():
    with psycopg.connect(**db_kwargs("agent","app"), autocommit=True) as conn:
        user = conn.execute("INSERT INTO users(username) VALUES(%s) RETURNING user_id", ("mcp-test-"+str(uuid4()),)).fetchone()[0]
        task = conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'MCP integration test','running') RETURNING task_id",(user,)).fetchone()[0]
        try:
            async def exercise():
                async with httpx.AsyncClient() as http:
                    assert (await http.post(MCP_URL)).status_code == 401
                    assert (await http.post(MCP_URL,headers={"Authorization":"Bearer wrong"})).status_code == 401
                async with MCPClient(MCP_URL,MCP_BEARER_TOKEN,str(task)) as client:
                    assert {t["function"]["name"] for t in client.tools} >= {"list_tables","describe_table","run_sql","get_result"}
                    assert len((await client.call("list_tables",{}))["tables"]) == 9
                    profile=await client.call('data_context',{})
                    assert profile['coverage']['available'] and profile['coverage']['partial_edge_months']==['2016-09','2018-10']
                    assert profile['dimension_precheck'] is True
                    assert (await client.call('check_dimension',{'column':'customer_state','value':'SP'}))['exists']
                    assert (await client.call('check_dimension',{'column':'customer_state','value':'XX'}))['error']=='unknown_dimension'
                    before=conn.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(task,)).fetchone()[0]
                    missing=await client.call('run_sql',{'sql':"SELECT count(*) AS n FROM customers WHERE customer_state='XX'"})
                    assert missing['error']=='unknown_dimension' and 'result_id' not in missing
                    assert conn.execute('SELECT count(*) FROM query_results WHERE task_id=%s',(task,)).fetchone()[0]==before
                    description = await client.call("describe_table",{"name":"orders"})
                    assert len(description["samples"]) == 3
                    assert any(c["name"] == "order_id" and c["comment"] for c in description["columns"])
                    result = await client.call("run_sql",{"sql":"SELECT order_id FROM orders ORDER BY order_id"})
                    assert result["row_count"] == 1000 and len(result["preview"]) == 20
                    assert 'dimension_checks' not in result  # valid SQL keeps Step 9 tool-result shape
                    stored = conn.execute("SELECT task_id,rows,row_count,data_version,sql FROM query_results WHERE result_id=%s",(result["result_id"],)).fetchone()
                    assert stored[0] == task and len(stored[1]) == stored[2] == 1000
                    assert stored[3] == result["data_version"] and stored[4].endswith("LIMIT 1000")
                    page = await client.call("get_result",{"result_id":result["result_id"],"offset":25,"limit":3})
                    assert page["preview"] == stored[1][25:28]
                    counts = await client.call("run_sql",{"sql":"SELECT count(*) AS n FROM orders"})
                    with psycopg.connect(**db_kwargs(role="reader")) as reader:
                        actual = reader.execute("SELECT count(*) FROM orders").fetchone()[0]
                    assert counts["preview"][0]["n"] == actual
                    assert counts["statistics"]["n"]["mean"] == str(actual)
                    for statement in ("DROP TABLE orders", "SELECT pg_sleep(1)", "SELECT unknown_column FROM orders",
                                      "SELECT order_id,order_id FROM orders"):
                        assert (await client.call("run_sql",{"sql":statement}))["error"] == "mcp_tool_error"
                    assert (await client.call("describe_table",{"name":"pg_authid"}))["error"] == "mcp_tool_error"
                    ident='declining_count_and_largest_drop'
                    state=await client.call('state_write',{'role':'planner','payload':{'subtasks':[{'id':ident,'question':'integration probe','depends_on':[]}]}})
                    assert ident in state['subtasks']
                    assert (await client.call('state_read',{}))['plan']['subtasks'][0]['id']==ident
                async with MCPClient(MCP_URL,MCP_BEARER_TOKEN,str(uuid4())) as client:
                    assert (await client.call("run_sql",{"sql":"SELECT 1"}))["error"] == "mcp_tool_error"
                    assert (await client.call("get_result",{"result_id":result["result_id"]}))["error"] == "mcp_tool_error"
            asyncio.run(exercise())
        finally:
            conn.execute("UPDATE tasks SET status='completed' WHERE task_id=%s",(task,))
