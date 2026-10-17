"""CPU multilingual embeddings behind the OpenAI embeddings wire format."""
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource
from pydantic import BaseModel, Field

MODEL="intfloat/multilingual-e5-small"
app=FastAPI()
lock=Lock()


@lru_cache(maxsize=1)
def encoder():
    TextEmbedding.add_custom_model(model=MODEL,pooling=PoolingType.MEAN,normalization=True,
        sources=ModelSource(hf=MODEL),dim=384,model_file="onnx/model.onnx")
    return TextEmbedding(model_name=MODEL,cache_dir=os.getenv("FASTEMBED_CACHE_PATH","/models"),threads=2)


class Input(BaseModel):
    model: str
    input: list[str] | str
    encoding_format: str="float"


@app.get("/health")
def health():
    return {"ready":True,"model":MODEL,"loaded":encoder.cache_info().currsize>0}


@app.post("/v1/embeddings")
def embeddings(body: Input):
    if body.model!=MODEL or body.encoding_format!="float": raise HTTPException(400,"Unsupported model/encoding")
    texts=[body.input] if isinstance(body.input,str) else body.input
    if not 1<=len(texts)<=128 or any(len(s)>12000 for s in texts): raise HTTPException(400,"Input size limit")
    with lock:
        model=encoder()
        vectors=list(model.embed(texts,batch_size=8))
    return {"object":"list","model":MODEL,"data":[{"object":"embedding","index":i,"embedding":v.tolist()} for i,v in enumerate(vectors)]}


@app.get("/model-info")
def model_info():
    from importlib.metadata import version
    encoder()
    files={}
    root=Path(os.getenv("FASTEMBED_CACHE_PATH","/models"))
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in {".onnx",".json",".txt"}:
            with p.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
            files[str(p.relative_to(root))]=digest
    return {"model":MODEL,"dimensions":384,"fastembed_version":version("fastembed"),"files_sha256":files}
