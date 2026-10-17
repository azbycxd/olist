"""Pinned local embedding identities shared with the independent model service."""
import os
import re

PROFILES = {
    "BAAI/bge-m3": {"revision": "5617a9f61b028005a4858fdac845db406aefb181", "dimensions": 1024,
        "pooling": "CLS", "model_file": "onnx/model.onnx",
        "additional_files": ["onnx/model.onnx_data", "onnx/Constant_7_attr__value"]},
    "intfloat/multilingual-e5-small": {"revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3", "dimensions": 384,
        "pooling": "MEAN", "model_file": "onnx/model.onnx", "additional_files": []},
}
MODEL = os.getenv("EMBEDDING_MODEL") or "BAAI/bge-m3"
REVISION = os.getenv("EMBEDDING_REVISION") or PROFILES[MODEL]["revision"]
BASE = os.getenv("EMBEDDING_BASE_URL") or "http://embeddings:8002/v1"
if not re.fullmatch(r"[0-9a-f]{40}", REVISION):
    raise ValueError("EMBEDDING_REVISION must be a full pinned commit SHA")


def provenance(used=False):
    """Record configuration even when disabled; verify the live identity when used."""
    result = {"model": MODEL, "revision": REVISION, "used": used, "service_verified": False}
    if used:
        import httpx
        response = httpx.get(BASE.rsplit('/v1', 1)[0] + '/model-info', timeout=300)
        response.raise_for_status()
        info = response.json()
        if info.get('model') != MODEL or info.get('revision') != REVISION:
            raise ValueError('Embedding service identity differs from configured model/revision')
        result.update(info, used=True, service_verified=True)
    return result
