"""Code-only date detection; a short warning only for out-of-coverage questions."""
import calendar
import re
from datetime import date
from config import boundary_guards_enabled

CLARIFY = '缺少时间范围等关键条件时，请求澄清或明确写出所用假设。'
TOKEN = re.compile(
    r'(?P<iso>(?:19|20)\d{2}[-/](?:1[0-2]|0?[1-9])(?:[-/](?:3[01]|[12]\d|0?[1-9]))?)(?!\d)'
    r'|(?P<year>(?:19|20)\d{2})\s*年?'
    r'|(?:Q(?P<q>[1-4])|第?(?P<cq>[一二三四1-4])\s*季度)'
    r'|(?P<half>[上下])半年'
    r'|(?P<month>1[0-2]|0?[1-9])\s*月(?:\s*(?P<day>[12]\d|3[01]|0?[1-9])\s*[日号])?', re.I)


def date_ranges(question, today=None):
    """Calendar intervals from ordinary date forms, never IDs or gold SQL.

    An unqualified year means a calendar year; subsequent quarters/months
    inherit the year. Unsupported prose is left to the clarification rule.
    """
    today=today or date.today()
    for word,year in [('今年',today.year),('去年',today.year-1),('明年',today.year+1)]:
        question=question.replace(word,f'{year}年')
    for word,delta in [('本月',0),('上月',-1),('下月',1)]:
        n=today.year*12+today.month-1+delta
        question=question.replace(word,f'{n//12}年{n%12+1}月')
    ranges=[];year=None;qualified=False
    def period(y,m=1,last=12,d=None):
        try:return (date(y,m,d or 1),date(y,last,d or calendar.monthrange(y,last)[1]))
        except ValueError:return None
    def add(value):
        if value and value not in ranges:ranges.append(value)
    for match in TOKEN.finditer(question):
        if match['year'] or match['iso']:
            if year and not qualified:add(period(year))
            qualified=False
            if match['iso']:
                parts=[int(x) for x in re.split('[-/]',match['iso'])]
                year=parts[0];qualified=True
                add(period(year,parts[1],parts[1],parts[2] if len(parts)>2 else None))
            else:year=int(match['year'])
        elif year:
            if match['q'] or match['cq']:
                value=match['q'] or match['cq'];q=int(value) if value.isdigit() else '一二三四'.index(value)+1
                add(period(year,q*3-2,q*3));qualified=True
            elif match['half']:
                add(period(year,1 if match['half']=='上' else 7,6 if match['half']=='上' else 12));qualified=True
            elif match['month']:
                m=int(match['month']);add(period(year,m,m,int(match['day']) if match['day'] else None));qualified=True
    if year and not qualified:add(period(year))
    return ranges


def context(question, profile=None):
    if not boundary_guards_enabled():return ''
    text='\n'+CLARIFY
    ranges=date_ranges(question)
    if not ranges:return text
    c=(profile or {}).get('coverage',{})
    if not c.get('available'):raise RuntimeError('Dataset coverage unavailable')
    start,end=date.fromisoformat(c['start_date']),date.fromisoformat(c['end_date'])
    if any(lo<start or hi>end for lo,hi in ranges):
        text+=f'\n时间范围提示：记录仅覆盖 {start} 至 {end}；所问日期包含范围外时期，不能当作完整期间或以无记录断言业务为零。'
    return text


async def prepare_context(question, remote, emit):
    if not boundary_guards_enabled():return ''
    profile=await remote.call('data_context',{}) if date_ranges(question) else None
    text=context(question,profile)
    emit('data_boundary_context',{'mode':'conditional','injected_lines':text.strip().splitlines(),
                                  'coverage_warning':len(text.strip().splitlines())>1})
    return text


def has_time_scope(question):
    return bool(re.search(r'(?:19|20)\d{2}|\d+\s*[年月日天周季]|去年|今年|明年|上月|本月|下月|最近|近[一二三四五六七八九十]|所有时间|全时间|全部历史|全历史|历年|截至|至今',question))


def make_assumption_explicit(response,question,profile=None):
    if not boundary_guards_enabled() or has_time_scope(question):return response
    body=str(response.answer)
    if re.search(r'请.{0,12}(?:时间|日期|期间|范围)|(?:时间|日期|期间|范围).{0,12}(?:请|确认|指定)|假设|未找到|无法|不能|无权|不支持',body):return response
    assumptions=[c.text for c in response.claims if '假设' in c.text]
    if assumptions:
        if isinstance(response.answer,str):response.answer='采用的口径与假设：'+assumptions[0]+'\n'+response.answer
        return response
    # Never assert that an arbitrary SQL used the entire range: it might have
    # applied a saved preference or a narrower period. Fail to clarification.
    response.answer='请指定时间范围，或确认使用数据集全部已记录时期后再查询。'
    response.claims=[]
    return response


def unknown_dimension_response(result):
    from contracts import FinalAnswer
    values='、'.join(f"{r['dimension']}={r['value']}" for r in result['missing'])
    return FinalAnswer(answer=f'未找到该值：{values}。请核对名称或代码；未找到记录不能解释为现实业务数量为零。',claims=[])
