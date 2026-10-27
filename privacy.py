"""Deterministic event-text redaction; business result objects remain untouched."""
import re

EMAIL=re.compile(r'(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])')
PHONE=re.compile(r'(?<![A-Za-z0-9_.])(?:\+?86[- ]?)?1[3-9]\d{9}(?![A-Za-z0-9_.])|(?<![A-Za-z0-9_.])(?:\+55[- ]?)?\(?[1-9]\d\)?[- ]?9\d{4}[- ]\d{4}(?![A-Za-z0-9_.])')
IDENTITY=re.compile(r'(?<![A-Za-z0-9_])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?![A-Za-z0-9_])')
CPF=re.compile(r'(?<![A-Za-z0-9_])\d{3}\.\d{3}\.\d{3}-\d{2}(?![A-Za-z0-9_])|(?<=CPF: )\d{11}(?![A-Za-z0-9_])|(?<=CPF )\d{11}(?![A-Za-z0-9_])',re.I)
BARE_CPF=re.compile(r'(?<![A-Za-z0-9_.])\d{11}(?![A-Za-z0-9_.])')


def cpf_match(match):
    digits=[int(c) for c in match.group()]
    if len(set(digits))==1:return match.group()
    for length in (9,10):
        remainder=sum(digits[i]*(length+1-i) for i in range(length))%11
        if digits[length]!=(0 if remainder<2 else 11-remainder):return match.group()
    return '[CPF]'


def redact(value):
    if isinstance(value,str):
        for pattern,label in ((EMAIL,'EMAIL'),(IDENTITY,'ID'),(CPF,'CPF'),(PHONE,'PHONE')):
            value=pattern.sub('['+label+']',value)
        return BARE_CPF.sub(cpf_match,value)
    if isinstance(value,dict):return {k:redact(v) for k,v in value.items()}
    if isinstance(value,list):return [redact(v) for v in value]
    if isinstance(value,tuple):return tuple(redact(v) for v in value)
    return value
