"""Offline packaging guard for root modules used by production event writers."""
from pathlib import Path
import shlex


def test_image_copies_root_runtime_modules():
    root=Path(__file__).resolve().parents[1]
    sources=set()
    for line in (root/'Dockerfile').read_text(encoding='utf-8').splitlines():
        parts=shlex.split(line)
        if parts and parts[0]=='COPY' and parts[-1]=='./':sources.update(parts[1:-1])
    assert {'config.py','contracts.py','db_pool.py','telemetry.py','privacy.py'}<=sources
