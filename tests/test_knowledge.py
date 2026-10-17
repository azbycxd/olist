import asyncio
import pytest

from agent.retrieval import ToolView
from mcp_olist.knowledge import bm25,fuse,chunks


def test_semantic_chunking_and_rank_fusion():
    records=chunks()
    assert len(records)==32 and len({r['chunk_id'] for r in records})==32
    assert all('```sql' in r['content'] and r['content'].count('```')==2 for r in records if r['source']=='kb/metrics.md')
    assert bm25('签收时间',['无关商品','补录签收时间'])[0]==1
    assert fuse(['a','b','c'],['b','a','c'])==['a','b','c']


def test_disabled_knowledge_tool_cannot_be_guessed():
    class Remote:
        tools=[{'function':{'name':'search_knowledge'}}]
        async def call(self,*args): raise AssertionError('must not reach server')
    view=ToolView(Remote(),{'search_knowledge'})
    assert view.tools==[]
    with pytest.raises(ValueError): asyncio.run(view.call('search_knowledge',{}))
