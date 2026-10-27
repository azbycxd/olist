"""Compose health check: agent DB only; never initializes the olist pool."""
import json
import time
import tempfile
from pathlib import Path
from config import WORKER_HEARTBEAT_SECONDS


PATH=Path(tempfile.gettempdir())/'olist-worker-health.json'


def write_heartbeat(status):
    # Written only AFTER the pooled agent-DB heartbeat commits. Healthcheck
    # processes don't open extra connections beyond the declared pool cap.
    temporary=PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps({'status':status,'at':time.time()}),encoding='utf-8')
    temporary.replace(PATH)


def main():
    try:
        state=json.loads(PATH.read_text(encoding='utf-8'))
        return 0 if state['status']=='ready' and 0<=time.time()-state['at']<WORKER_HEARTBEAT_SECONDS*3 else 1
    except (OSError,ValueError,KeyError):
        return 1


if __name__=='__main__':
    raise SystemExit(main())
