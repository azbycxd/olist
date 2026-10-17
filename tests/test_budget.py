import asyncio
from types import SimpleNamespace

from agent.model import Budget,ACTIVE_BUDGET,request
from test_agent import completion


def test_shared_budget_includes_non_agent_roles_and_blocks_further_calls():
    calls=[]
    async def create(**kwargs):calls.append(kwargs);return completion(tokens=12)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    async def exercise():
        budget=Budget(20);token=ACTIVE_BUDGET.set(budget)
        try:
            for role in ['agent','preference_extractor','reviewer']:
                await request(client,'test',[{'role':'user','content':'test'}],lambda *args:None,role=role)
            assert budget.used==24 and len(calls)==2
        finally:ACTIVE_BUDGET.reset(token)
    asyncio.run(exercise())


def test_missing_usage_cannot_be_claimed_as_zero():
    async def create(**kwargs):return completion(tokens=None)
    async def exercise():
        budget=Budget(20);token=ACTIVE_BUDGET.set(budget)
        try:
            await request(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
                'test',[{'role':'user','content':'test'}],lambda *args:None)
            assert not budget.complete
        finally:ACTIVE_BUDGET.reset(token)
    asyncio.run(exercise())
