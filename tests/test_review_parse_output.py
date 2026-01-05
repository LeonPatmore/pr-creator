from __future__ import annotations

import sys
from pathlib import Path



def test_parse_review_prefers_final_verdict_marker() -> None:
    output = """
IMPORTANT OUTPUT FORMAT (no extra text):
- If the repo is ready, output exactly: READY_TO_COMMIT
- Otherwise output exactly: CHANGES_REQUIRED\\n<bullet list of required changes>

Some reasoning...

CHANGES_REQUIRED
- do the required thing
""".strip()
    needs_changes, feedback = _parse_review_output(output)
    assert needs_changes is True
    assert feedback == "- do the required thing"
