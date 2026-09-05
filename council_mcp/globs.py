"""Path/glob matching for `scope`, `context_files` and `never_share`.

Patterns are POSIX-style relative to the repo root. Supported forms:
  `src/api/`        directory prefix (everything below)
  `src/api/x.py`    exact file
  `*.sql`           basename glob (any directory)
  `secrets/**`      recursive glob; `**` matches zero or more path segments
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import PurePosixPath


def norm(path: str) -> str:
    raw = path.replace("\\", "/")
    out = PurePosixPath(raw).as_posix()
    if out.startswith("./"):
        out = out[2:]
    if raw.endswith("/") and not out.endswith("/"):
        out += "/"
    return out.lstrip("/")


@lru_cache(maxsize=1024)
def _regex(pattern: str) -> re.Pattern[str]:
    pat = norm(pattern)
    if pat.endswith("/"):
        return re.compile(re.escape(pat) + ".*")
    if "/" not in pat:  # basename glob: match in any directory
        pat = "**/" + pat
    out = []
    i = 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pat.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out))


def matches(path: str, patterns: list[str]) -> bool:
    p = norm(path)
    return any(_regex(g).fullmatch(p) for g in patterns)


def overlap(a: list[str], b: list[str]) -> list[str]:
    """Patterns in `a` that could touch the same files as patterns in `b` (conservative)."""
    hits = []
    for x in a:
        nx = norm(x)
        for y in b:
            ny = norm(y)
            if nx == ny or matches(nx.rstrip("/"), [y]) or matches(ny.rstrip("/"), [x]):
                hits.append(x)
                break
            if nx.endswith("/") and ny.startswith(nx) or ny.endswith("/") and nx.startswith(ny):
                hits.append(x)
                break
    return hits
