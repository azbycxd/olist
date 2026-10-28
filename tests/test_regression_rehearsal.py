"""The preflight must exercise all real evaluator cases and SQL event writers."""
import pytest


def test_rehearsal_requires_all_cases_without_engineering_errors():
    from scripts.step12_rehearsal import validate_rehearsal
    ids=[f'q{i}' for i in range(31)]
    rows=[{'question_id':i,'task_id':i,'termination':'final_answer','correct':False} for i in ids]
    validate_rehearsal(rows,ids,{i:2 for i in ids})
    with pytest.raises(ValueError):validate_rehearsal(rows[:-1],ids,{i:2 for i in ids})
    with pytest.raises(ValueError):validate_rehearsal([{**rows[0],'error':'UniqueViolation'},*rows[1:]],ids,{i:2 for i in ids})
    with pytest.raises(ValueError):validate_rehearsal(rows,ids,{i:0 for i in ids})


def test_rehearsal_http_responses_cover_parallel_sql_and_memory():
    from scripts.step12_rehearsal import response_message
    message=response_message({'messages':[]})
    assert [c['function']['name'] for c in message['tool_calls']]==['run_sql','run_sql']
    final=response_message({'messages':[{'role':'tool','name':'run_sql','content':'{"result_id":"fixture"}'}]})
    assert final['tool_calls'][0]['function']['name']=='final_answer'
    assert response_message({'response_format':{'type':'json_object'}})['content']=='{"preferences": []}'
