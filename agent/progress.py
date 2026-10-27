"""Deterministic loop guards shared by the runtime and read-only trace replay."""
from collections import deque
import json
from agent.sql_normalize import normalize_sql
from config import NO_PROGRESS_WINDOW, NO_PROGRESS_EMPTY_TURNS, REPEATED_CALL_LIMIT


def signature(name, arguments):
    try: args = json.loads(arguments) if isinstance(arguments,str) else arguments
    except (ValueError,TypeError): args = arguments
    if name=='run_sql' and isinstance(args,dict) and isinstance(args.get('sql'),str):
        args = {**args, 'sql':normalize_sql(args['sql'])}
    return name,json.dumps(args,sort_keys=True,ensure_ascii=False)


class Progress:
    def __init__(self):
        self.streaks = {}
        self.turns = deque(maxlen=NO_PROGRESS_WINDOW)
        self.empty_turns = 0
        self.result_ids = set()

    def before(self, calls):
        signatures = [signature(name,args) for name,args in calls]
        self.streaks = {s:self.streaks.get(s,0)+signatures.count(s) for s in set(signatures)}
        self.turns.append(set(signatures))
        if any(n>=REPEATED_CALL_LIMIT for n in self.streaks.values()): return 'consecutive_repeat'
        if len(self.turns)==NO_PROGRESS_WINDOW and all(self.turns) and len(set.union(*self.turns))<=2:
            return 'alternating_window'

    def after(self, results):
        ids = {r['result_id'] for r in results if r.get('result_id') and
               isinstance(r.get('row_count'), (int,float)) and r['row_count']>0}
        fresh = ids-self.result_ids
        self.result_ids.update(ids)
        empty = bool(results) and all(r.get('error') or r.get('row_count')==0 or
            ('preview' in r and r['preview']==[]) or ('rows' in r and r['rows']==[]) for r in results)
        self.empty_turns = self.empty_turns+1 if empty and not fresh else 0
        if self.empty_turns>=NO_PROGRESS_EMPTY_TURNS: return 'empty_or_error'
