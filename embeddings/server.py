"""Pinned CPU embeddings behind the OpenAI embeddings wire format."""
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource
from huggingface_hub import snapshot_download
from pydantic import BaseModel
from embedding_config import MODEL, REVISION, PROFILES

app = FastAPI()
lock = Lock()
PROFILE = PROFILES[MODEL]
FILES = [PROFILE['model_file'], *PROFILE['additional_files'], 'config.json',
         'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'sentencepiece.bpe.model']
ROOT = Path(os.getenv('FASTEMBED_CACHE_PATH', '/models')) / MODEL.replace('/', '--') / REVISION
load_seconds = None


@lru_cache(maxsize=1)
def encoder():
    global load_seconds
    started = perf_counter()
    if not all((ROOT / name).is_file() for name in FILES):
        snapshot_download(repo_id=MODEL, revision=REVISION, local_dir=ROOT,
            allow_patterns=FILES, endpoint=os.getenv('HF_ENDPOINT', 'https://hf-mirror.com'), max_workers=2)
    if not all((ROOT / name).is_file() for name in FILES):
        raise RuntimeError('Pinned model snapshot is incomplete')
    TextEmbedding.add_custom_model(model=MODEL, pooling=getattr(PoolingType, PROFILE['pooling']),
        normalization=True, sources=ModelSource(hf=MODEL), dim=PROFILE['dimensions'],
        model_file=PROFILE['model_file'], additional_files=PROFILE['additional_files'])
    result = TextEmbedding(model_name=MODEL, cache_dir=str(ROOT.parent), specific_model_path=str(ROOT),
        local_files_only=True, providers=['CPUExecutionProvider'], threads=2)
    load_seconds = perf_counter() - started
    return result


class Input(BaseModel):
    model: str
    input: list[str] | str
    encoding_format: str = 'float'


@app.get('/health')
def health():
    return {'ready': True, 'model': MODEL, 'revision': REVISION, 'loaded': encoder.cache_info().currsize > 0}


@app.post('/v1/embeddings')
def embeddings(body: Input):
    if body.model != MODEL or body.encoding_format != 'float':
        raise HTTPException(400, 'Unsupported model/encoding')
    texts = [body.input] if isinstance(body.input, str) else body.input
    if not 1 <= len(texts) <= 128 or any(not s or len(s) > 12000 for s in texts):
        raise HTTPException(400, 'Input size limit')
    with lock:
        vectors = list(encoder().embed(texts, batch_size=2))
    return {'object': 'list', 'model': MODEL, 'revision': REVISION,
        'data': [{'object': 'embedding', 'index': i, 'embedding': v.tolist()} for i, v in enumerate(vectors)]}


@lru_cache(maxsize=1)
def manifest():
    from importlib.metadata import version
    files = {}
    for name in FILES:
        with (ROOT / name).open('rb') as stream:
            files[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'model': MODEL, 'revision': REVISION, 'dimensions': PROFILE['dimensions'],
        'pooling': PROFILE['pooling'], 'normalization': True, 'provider': 'CPUExecutionProvider',
        'threads': 2, 'batch_size': 2, 'fastembed_version': version('fastembed'),
        'onnxruntime_version': version('onnxruntime'), 'hf_endpoint': os.getenv('HF_ENDPOINT'),
        'files_sha256': files, 'load_seconds': load_seconds}


@app.get('/model-info')
def model_info():
    with lock:
        encoder()
        return manifest()
