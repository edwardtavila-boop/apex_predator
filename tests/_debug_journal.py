from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from eta_engine.brain.avengers import (
    BackgroundTask,
    AvengerDaemon,
    Fleet,
)
from eta_engine.brain.avengers.daemon import _run_local_background_task

tmp = Path(tempfile.mkdtemp())
journal = tmp / "test.jsonl"

result = _run_local_background_task(BackgroundTask.PROMPT_WARMUP)
print(f"Stub result: {result}")
print(f"Has billing_mode: {'billing_mode' in result}")

os.remove(str(journal))
tmp.rmdir()
