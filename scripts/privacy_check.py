"""Fail if tracked files contain private data: user home paths, private IPs, e-mails, tokens.

Run before pushing: `uv run python scripts/privacy_check.py` (CI runs it too).
Allowlist patterns in `.privacy-allow` (one regex per line) for legitimate mentions.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "windows user path": re.compile(r"[A-Za-z]:\\+Users\\+(?!<)[A-Za-z0-9._-]+\\"),
    "posix home path": re.compile(r"/(?:home|Users)/(?!<)[A-Za-z0-9._-]+/"),
    "short 8.3 temp path": re.compile(r"[A-Z0-9]{4,6}~\d"),
    "private ip": re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "e-mail": re.compile(
        r"\b[A-Za-z0-9._%+-]+@(?!example\.|localhost)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "token-like": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
}
SKIP = {"uv.lock"}
TEXT_EXT = {
    ".md",
    ".py",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".j2",
    ".cfg",
    ".ini",
    ".html",
    ".css",
    ".js",
}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [Path(p) for p in out.decode().split("\0") if p]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    allow = (
        [
            re.compile(ln)
            for ln in (root / ".privacy-allow").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        if (root / ".privacy-allow").exists()
        else []
    )
    hits = 0
    for f in tracked_files():
        if f.name in SKIP or f.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = (root / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for kind, rx in PATTERNS.items():
                for m in rx.finditer(line):
                    if any(a.search(m.group(0)) for a in allow):
                        continue
                    hits += 1
                    print(f"{f}:{i}: {kind}: {m.group(0)}")
    if hits:
        print(
            f"\n{hits} private-data hit(s). Replace with placeholders (<user>, <srv-ai>, "
            f"user@example.com) or allowlist in .privacy-allow."
        )
        return 1
    print("privacy check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
