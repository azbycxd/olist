"""Semantic chunks, jieba BM25, pgvector cosine ranking and reciprocal-rank fusion."""
import hashlib
import json
import math
import os
import re
from collections import Counter

import jieba
import psycopg
from openai import OpenAI

from config import ROOT,db_kwargs

MODEL=os.getenv("EMBEDDING_MODEL") or "intfloat/multilingual-e5-small"
BASE=os.getenv("EMBEDDING_BASE_URL") or "http://embeddings:8002/v1"


def chunks():
    result=[]
    for path in sorted((ROOT/"kb").glob("*.md")):
        for block in re.split(r"(?m)^## ",path.read_text(encoding="utf-8"))[1:]:
            title,_,body=block.partition("\n")
            ident=title.split(" ",1)[0]
            if not re.fullmatch(r"[a-z][a-z0-9_]+",ident): raise ValueError("Chunk needs stable ID")
            content=title+"\n"+body.strip()
            result.append({"chunk_id":ident,"source":"kb/"+path.name,"content":content,
                "content_sha256":hashlib.sha256(content.encode()).hexdigest()})
    if not result or len({x['chunk_id'] for x in result})!=len(result): raise ValueError("Empty/duplicate knowledge chunks")
    return result


def embed(texts,query=False):
    prefix=("query: " if query else "passage: ") if "e5" in MODEL else ""
    with OpenAI(base_url=BASE,api_key=os.getenv("EMBEDDING_API_KEY") or "local",timeout=300,max_retries=2) as client:
        response=client.embeddings.create(model=MODEL,input=[prefix+t for t in texts],encoding_format="float")
    vectors=[item.embedding for item in sorted(response.data,key=lambda x:x.index)]
    if len(vectors)!=len(texts) or len({len(v) for v in vectors})!=1 or not all(v and all(math.isfinite(n) for n in v) for v in vectors):
        raise ValueError("Invalid embedding response")
    return vectors


def tokens(text):
    return [t.lower() for t in jieba.lcut(text) if re.search(r"\w",t)]


def bm25(query,documents):
    corpus=[Counter(tokens(d)) for d in documents]
    lengths=[sum(c.values()) for c in corpus]
    average=sum(lengths)/len(lengths) if lengths else 1
    scores=[0.0]*len(corpus)
    for term in set(tokens(query)):
        df=sum(term in c for c in corpus)
        idf=math.log(1+(len(corpus)-df+0.5)/(df+0.5))
        for i,c in enumerate(corpus):
            f=c[term]
            scores[i]+=idf*f*2.5/(f+1.5*(0.25+0.75*lengths[i]/average)) if f else 0
    return sorted(range(len(corpus)),key=lambda i:(-scores[i],i))


def fuse(*rankings):
    score={}
    for ranking in rankings:
        for rank,ident in enumerate(ranking,1): score[ident]=score.get(ident,0)+1/(60+rank)
    return sorted(score,key=lambda i:(-score[i],i))


def rebuild():
    records=chunks()
    vectors=embed([r["content"] for r in records])
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(730019)")
        conn.execute("DELETE FROM knowledge_chunks")
        for row,vector in zip(records,vectors):
            conn.execute("INSERT INTO knowledge_chunks(chunk_id,source,content,content_sha256,embedding,embedding_model,dimensions) VALUES(%s,%s,%s,%s,%s::vector,%s,%s)",
                (row['chunk_id'],row['source'],row['content'],row['content_sha256'],json.dumps(vector),MODEL,len(vector)))
    return {"chunks":len(records),"embedding_model":MODEL,"dimensions":len(vectors[0]),"contents":[{k:v for k,v in r.items() if k!='content'} for r in records]}


def search(query,method="hybrid",limit=3):
    if method not in {"bm25","vector","hybrid"} or not 1<=limit<=10: raise ValueError("Invalid retrieval settings")
    if not query.strip() or len(query)>6000: raise ValueError("Query must contain 1..6000 characters")
    with psycopg.connect(**db_kwargs("agent","app")) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        records=conn.execute("SELECT chunk_id,source,content,content_sha256,embedding_model,dimensions FROM knowledge_chunks ORDER BY chunk_id").fetchall()
        if not records or any(r[4]!=MODEL for r in records): raise ValueError("Rebuild knowledge index for the configured model")
        keyword=[records[i][0] for i in bm25(query,[r[2] for r in records])] if method!='vector' else []
        vector=[]
        if method!='bm25':
            embedding=embed([query],query=True)[0]
            if any(r[5]!=len(embedding) for r in records): raise ValueError("Embedding dimensions changed")
            vector=[r[0] for r in conn.execute("SELECT chunk_id FROM knowledge_chunks ORDER BY embedding <=> %s::vector,chunk_id",(json.dumps(embedding),)).fetchall()]
    order=keyword if method=="bm25" else vector if method=="vector" else fuse(keyword,vector)
    lookup={r[0]:{"chunk_id":r[0],"source":r[1],"content":r[2],"content_sha256":r[3]} for r in records}
    return {"method":method,"embedding_model":MODEL,"chunks":[lookup[i] for i in order[:limit]]}
