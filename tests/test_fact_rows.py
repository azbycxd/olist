from contracts import FinalAnswer
from eval.scoring import score


def test_fact_row_arrays_and_contradictions():
    q={"answer_type":"key_facts"}
    audit={"claim_count":1,"unsupported_claims":0,"unsupported_numbers":0}
    def grade(value):
        return score(q,FinalAnswer(answer="report",claims=[{"text":"fact","value":value,"evidence":[]}]),{"n":42},audit)
    assert grade([{"n":42}])["fact_hits"]==1
    assert grade([{"n":42},{"n":-42}])["fact_hits"]==0
    assert grade([{"other_name":42}])["fact_hits"]==0
