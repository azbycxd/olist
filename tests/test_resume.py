import asyncio
from contracts import Claim,FinalAnswer
from agent.state import Plan,Board,Subtask,Decision
from agent import multi


def test_completed_subtasks_are_reused_without_planning_or_analysis(monkeypatch):
    plan=Plan(subtasks=[{'id':'a','question':'first'},{'id':'b','question':'second','depends_on':['a']}])
    claim=Claim(text='checked',value=42,evidence=[])
    board=Board(plan=plan,subtasks={p.id:Subtask(question=p.question,depends_on=p.depends_on,
        status='completed',claims=[claim],review=[Decision(claim_index=0,approved=True,reason='verified')]) for p in plan.subtasks})
    async def prepare(*a):return None,''
    async def forbidden(*a,**k):raise AssertionError('Completed checkpoints must not query or plan again')
    async def control(remote,name,args):
        if name=='state_write':
            assert args['role']=='writer'
            board.report=FinalAnswer.model_validate(args['payload'])
        return board
    async def write(*a):return 'verified'
    monkeypatch.setattr(multi,'prepare',prepare);monkeypatch.setattr(multi,'request',forbidden)
    monkeypatch.setattr(multi,'run_loop',forbidden);monkeypatch.setattr(multi,'control',control);monkeypatch.setattr(multi,'write',write)
    events=[]
    result=asyncio.run(multi.run_multi('q',None,None,'m',lambda *a:events.append(a),mode='multi',rag_mode='off',schema_mode='on_demand',memory_enabled=True,resume_board=board.model_dump()))
    assert result.termination=='final_answer'
    assert any(e[0]=='subtasks_reused' and e[1]['subtask_ids']==['a','b'] for e in events)


def test_scheduler_skips_completed_dependency():
    plan=Plan(subtasks=[{'id':'a','question':'first'},{'id':'b','question':'second','depends_on':['a']}])
    ran=[]
    async def execute(p):ran.append(p.id)
    asyncio.run(multi.schedule(plan,execute,completed=['a']))
    assert ran==['b']


def test_saved_queries_resume_review_without_requery(monkeypatch):
    plan=Plan(subtasks=[{'id':'a','question':'first'}])
    claim=Claim(text='checked',value=42,evidence=[])
    board=Board(plan=plan,subtasks={'a':Subtask(question='first',depends_on=[],status='completed',claims=[claim])})
    reviewed=[]
    async def prepare(*a):return None,''
    async def forbidden(*a,**k):raise AssertionError('Saved query result must not be recomputed')
    async def review(question,claims,*a):
        reviewed.append(claims)
        return [Decision(claim_index=0,approved=True,reason='verified')]
    async def control(remote,name,args):
        if name=='state_write':
            if args['role']=='reviewer':
                board.subtasks['a'].review=[Decision(**d) for d in args['payload']['decisions']]
            elif args['role']=='writer':board.report=FinalAnswer.model_validate(args['payload'])
            else:assert args['role']=='analyst' and args['payload']['status']=='completed'
        return board
    async def write(*a):return 'verified'
    for key,value in {'prepare':prepare,'request':forbidden,'run_loop':forbidden,'review':review,'control':control,'write':write}.items():
        monkeypatch.setattr(multi,key,value)
    result=asyncio.run(multi.run_multi('q',None,None,'m',lambda *a:None,mode='multi',rag_mode='off',schema_mode='on_demand',memory_enabled=True,resume_board=board.model_dump()))
    assert result.termination=='final_answer' and reviewed==[[claim]]
