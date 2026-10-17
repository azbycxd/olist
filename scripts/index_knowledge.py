"""Rebuild the KB atomically and retain a compact, hashed receipt."""
from mcp_olist.knowledge import rebuild, BASE
from scripts.common import start_log,record
from scripts.evidence import publish_log

if __name__=="__main__":
    logger,path=start_log("knowledge_index")
    record(logger,"index_rebuilt",**rebuild())
    if BASE.startswith("http://embeddings:"):
        import httpx
        record(logger,"local_model",**httpx.get(BASE.rsplit('/v1',1)[0]+"/model-info",timeout=120).json())
    print("Evidence:",publish_log(path).name)
