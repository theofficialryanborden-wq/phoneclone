"""Session debug logging (remove after investigation)."""

from __future__ import annotations

import json
import time
from pathlib import Path

_LOG = Path(__file__).resolve().parents[2] / "debug-9051dc.log"
_SESSION = "9051dc"


def agent_log(
    location: str,
    message: str,
    *,
    data: dict | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # #endregion
