"""Small command-line helpers shared by the data scripts."""

import json
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

from config import LOG_DIR


def start_log(name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = LOG_DIR / f"{name}_{stamp}_{uuid4().hex[:8]}.jsonl"
    logger = logging.getLogger(name + path.stem)
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.FileHandler(path, encoding="utf-8"))
    logger.addHandler(logging.StreamHandler(sys.stdout))
    return logger, path


def record(logger, event: str, **fields):
    logger.info(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "event": event, **fields},
                           ensure_ascii=False, default=str))
