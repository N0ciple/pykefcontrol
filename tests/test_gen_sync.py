"""The generated sync client/transport must be up to date with the async sources."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_generated_sync_code_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_sync.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
