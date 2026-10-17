from scripts.export_reports import render


def test_report_links_resolve_and_query_text_is_escaped():
    ref='12345678-1234-1234-1234-123456789012'
    case={'question_id':'test','task_id':ref,'question':'question <script>bad()</script>',
        'response':{'answer':f'[证据](#result-{ref}) <script>bad()</script>','claims':[]},'evidence':{}}
    page=render(case,{ref:{'sql':'SELECT 1 < 2','columns':['n'],'rows':[{'n':'<img onerror=bad>'}],'data_version':'test'}})
    assert f'href="#result-{ref}"' in page and f'id="result-{ref}"' in page
    assert '<script>' not in page and '<img' not in page and '&lt;img' in page
    assert 'question &lt;script&gt;bad()&lt;/script&gt;' in page
