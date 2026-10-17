"""Publish compact, immutable receipts derived from actual run logs."""

import hashlib
import json
from pathlib import Path

from config import ROOT

EVIDENCE_DIR = ROOT / "evidence"


def write_evidence(filename: str, data: dict):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / filename
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Evidence is immutable: {path.name}")
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return path


def publish_log(path: Path):
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retained = [r for r in records if r["event"] != "table_loaded"]
    return write_evidence(path.stem + ".summary.json", {
        "source_log": path.name,
        "source_log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "records": retained,
    })
