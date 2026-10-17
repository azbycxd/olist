import asyncio
import pytest
from types import SimpleNamespace

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


@pytest.mark.parametrize('revision', [None, '0'*40])
def test_embedding_response_revision_must_match(monkeypatch, revision):
    from mcp_olist import knowledge
    class Client:
        def __init__(self, **kwargs): self.embeddings=self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            return SimpleNamespace(model=knowledge.MODEL, revision=revision, data=[])
    monkeypatch.setattr(knowledge, 'OpenAI', Client)
    with pytest.raises(ValueError, match='revision'):
        knowledge.embed(['test'])


def test_disabled_embedding_provenance_does_not_contact_service(monkeypatch):
    import httpx
    from mcp_olist.embedding_config import provenance, MODEL, REVISION
    def fail(*args, **kwargs): raise AssertionError('Disabled embeddings must not require a service')
    monkeypatch.setattr(httpx, 'get', fail)
    assert provenance() == {'model': MODEL, 'revision': REVISION, 'used': False, 'service_verified': False}


def test_live_embedding_identity_cannot_be_silently_substituted(monkeypatch):
    import httpx
    from mcp_olist.embedding_config import provenance, MODEL
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200,
        request=httpx.Request('GET', 'http://test/model-info'), json={'model': MODEL, 'revision': '0'*40}))
    with pytest.raises(ValueError, match='identity'):
        provenance(used=True)


def test_weighted_rrf_downweights_keyword_rank():
    assert fuse(["a","b"],["b","a"],weights=[0.25,1])==["b","a"]
    with pytest.raises(ValueError): fuse(["a"],weights=[-1])
