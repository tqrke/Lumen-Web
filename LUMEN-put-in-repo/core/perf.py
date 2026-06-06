"""Performance diagnostics for LUMEN — timings, memory, session stats."""

from __future__ import annotations

import json
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

_LOG_PATH = Path.home() / ".lumen" / "perf.log"
_SESSION: dict[str, Any] = {
    "started": time.time(),
    "spans": {},
    "counts": {},
}


def _write(line: str) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")
    except OSError:
        pass


def mark(event: str, **fields: Any) -> None:
    parts = [event]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    _write(" ".join(parts))


def count(name: str, n: int = 1) -> None:
    _SESSION["counts"][name] = int(_SESSION["counts"].get(name, 0)) + n


@contextmanager
def perf_span(name: str, *, log: bool = True, slow_ms: float = 120.0):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        bucket = _SESSION["spans"].setdefault(name, {"n": 0, "total_ms": 0.0, "max_ms": 0.0})
        bucket["n"] += 1
        bucket["total_ms"] += ms
        bucket["max_ms"] = max(bucket["max_ms"], ms)
        if log and ms >= slow_ms:
            _write(f"SLOW {name} {ms:.0f}ms")


def memory_snapshot(label: str = "snapshot") -> dict[str, float]:
    rss_mb = 0.0
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
        rss_mb = current / (1024 * 1024)
        mark("mem", label=label, current_mb=f"{rss_mb:.1f}", peak_mb=f"{peak / (1024 * 1024):.1f}")
    else:
        mark("mem", label=label, note="tracemalloc-off")
    return {"rss_mb": rss_mb}


def start_tracing() -> None:
    if not tracemalloc.is_tracing():
        tracemalloc.start(25)


def session_summary() -> str:
    uptime = time.time() - float(_SESSION["started"])
    lines = [f"uptime={uptime:.0f}s"]
    for name, bucket in sorted(_SESSION["spans"].items()):
        n = max(int(bucket.get("n", 0)), 1)
        avg = float(bucket.get("total_ms", 0.0)) / n
        lines.append(f"{name}: n={n} avg={avg:.0f}ms max={bucket.get('max_ms', 0):.0f}ms")
    for name, n in sorted(_SESSION["counts"].items()):
        lines.append(f"{name}={n}")
    summary = " | ".join(lines)
    _write(f"SESSION {summary}")
    return summary


def dump_session_json() -> None:
    try:
        out = Path.home() / ".lumen" / "perf_session.json"
        out.write_text(json.dumps(_SESSION, indent=2), encoding="utf-8")
    except OSError:
        pass
