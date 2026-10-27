import asyncio
import json
from types import SimpleNamespace

import pytest

from agent.mcp_client import MCPClient


def test_internal_state_and_review_reads_are_traced_without_headers():
    events=[]
    client=MCPClient('http://test','private-bearer-token','task',lambda *args:events.append(args))
    class Session:
        async def call_tool(self,name,arguments,**kwargs):
            return SimpleNamespace(isError=False,structuredContent={'ok':True,'result_id':'ref'})
    client.session=Session()
    for tool in ['state_read','state_write','get_result']:
        assert asyncio.run(client.call(tool,{}))['ok']
    assert [e[0] for e in events]==['mcp_call','mcp_result']*3
    assert all(events[i][1]['call_id']==events[i+1][1]['call_id'] for i in range(0,6,2))
    assert 'private-bearer-token' not in json.dumps(events)


def test_failed_mcp_dispatch_keeps_a_paired_trace():
    events=[]
    client=MCPClient('http://test','token','task',lambda *args:events.append(args))
    class Session:
        async def call_tool(self,*args,**kwargs):raise TimeoutError('timeout')
    client.session=Session()
    with pytest.raises(TimeoutError):asyncio.run(client.call('get_result',{}))
    assert events[1][1]['call_id']==events[0][1]['call_id']
    assert events[1][1]['error']=='TimeoutError' and events[1][3]>=0
