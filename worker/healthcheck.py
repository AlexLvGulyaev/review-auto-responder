"""Docker healthcheck для review-worker — проверяет свежесть heartbeat.json.

Worker пишет heartbeat.json каждую итерацию цикла (каждые WORKER_POLL_INTERVAL
секунд). Healthcheck считает воркер здоровым, если heartbeat свежий — его
mtime/last_iteration_at не старше WORKER_HEALTHCHECK_MAX_AGE секунд (по умолчанию
60 — покрывает 6 циклов опроса при интервале 10 с, давая запас на долгий LLM-запрос).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    path = Path(os.environ.get("HEARTBEAT_FILE_PATH", "data/heartbeat.json"))
    max_age = float(os.environ.get("WORKER_HEALTHCHECK_MAX_AGE", "60"))

    if not path.exists():
        print(f"healthcheck FAIL: heartbeat file not found at {path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"healthcheck FAIL: cannot read heartbeat: {exc}", file=sys.stderr)
        return 1

    stamp = data.get("last_iteration_at")
    if not stamp:
        print("healthcheck FAIL: last_iteration_at missing", file=sys.stderr)
        return 1

    try:
        parsed = time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%f%z"))
    except (ValueError, TypeError):
        # Fallback на mtime файла, если парсинг ISO со смещением не удался.
        parsed = path.stat().st_mtime

    age = time.time() - parsed
    if age > max_age:
        print(
            f"healthcheck FAIL: heartbeat is {age:.0f}s old (max {max_age:.0f}s)",
            file=sys.stderr,
        )
        return 1

    print(f"healthcheck OK: heartbeat {age:.0f}s old")
    return 0


if __name__ == "__main__":
    sys.exit(main())