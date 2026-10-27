"""Context guard must stop before admission/network and compact at most once."""
import asyncio
from types import SimpleNamespace
import pytest


def test_context_preflight_stops_without_any_model_request(monkeypatch):
    import config
    from agent.model import request
    from agent.task_control import ModelStopped
    from test_agent import completion
    monkeypatch.setattr(config,'CONTEXT_PREFLIGHT',True,raising=False)
    monkeypatch.setattr(config,'CONTEXT_TOKEN_COEFFICIENT',1.,raising=False)
    monkeypatch.setattr(config,'CONTEXT_LIMIT',100)
    called=[]
    async def create(**kwargs):called.append(kwargs);return completion([])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(ModelStopped,match='context_limit_preflight'):
        asyncio.run(request(client,'scripted',[{'role':'user','content':'x'*1000}],lambda *a:None))
    assert not called


def test_context_mask_once_then_send_preserves_original_messages(monkeypatch):
    import config
    from agent.model import request
    from agent.tools import untrusted
    from test_agent import completion
    monkeypatch.setattr(config,'CONTEXT_PREFLIGHT',True,raising=False)
    monkeypatch.setattr(config,'CONTEXT_TOKEN_COEFFICIENT',1.,raising=False)
    monkeypatch.setattr(config,'CONTEXT_LIMIT',2000)
    monkeypatch.setattr(config,'CONTEXT_KEEP_TURNS',1)
    messages=[{'role':'system','content':'s'},{'role':'user','content':'q'},
              {'role':'assistant','content':'a'},{'role':'tool','content':untrusted({'preview':'x'*8000})},
              {'role':'assistant','content':'next'}]
    calls=[];events=[]
    async def create(**kwargs):calls.append(kwargs);return completion([])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    asyncio.run(request(client,'scripted',messages,lambda kind,*args:events.append(kind),remaining=64))
    assert len(calls)==1 and len(calls[0]['messages'][3]['content'])<500
    assert len(messages[3]['content'])>8000 and events.count('context_preflight')==1


def test_conservative_coefficient_uses_95th_quantile_not_mean():
    from scripts.fit_context import fit
    report=fit([{'characters':100,'prompt_tokens':50} for _ in range(95)]+[{'characters':100,'prompt_tokens':90} for _ in range(5)])
    assert report['coefficient']==.5
    assert report['coverage']>=.95 and report['max_underestimate_tokens']==40
