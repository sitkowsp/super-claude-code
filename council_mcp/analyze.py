"""`/council:analyze` (DESIGN.md §14.3): deterministic repo scan → facts + proposed gates/routing.

No model calls. Same input → same output, so the result is reviewable and repeatable.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

LANG_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".fml": "formula",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
}
MANIFESTS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
}
SENSITIVE = ("config", "secret", "merit", "nuco", "receptur", ".env", "credential", "private")
SKIP_DIRS = {
    ".git",
    ".council",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "target",
    "bin",
    "obj",
}
GATES = {
    "python": {
        "before_review": ["uv run ruff check .", "uv run pytest -q"],
        "after_merge": ["uv run ruff check .", "uv run mypy", "uv run pytest -q"],
    },
    "typescript": {
        "before_review": ["npx eslint .", "npx tsc --noEmit", "npx vitest run"],
        "after_merge": ["npx eslint .", "npx tsc --noEmit", "npx vitest run"],
    },
    "javascript": {"before_review": ["npm test"], "after_merge": ["npm test"]},
    "csharp": {
        "before_review": ["dotnet build -warnaserror", "dotnet test"],
        "after_merge": [
            "dotnet format --verify-no-changes",
            "dotnet build -warnaserror",
            "dotnet test",
        ],
    },
    "go": {
        "before_review": ["go vet ./...", "go test ./..."],
        "after_merge": ["go vet ./...", "go test ./..."],
    },
    "rust": {
        "before_review": ["cargo clippy -- -D warnings", "cargo test"],
        "after_merge": ["cargo fmt --check", "cargo clippy -- -D warnings", "cargo test"],
    },
}


class Analysis(BaseModel):
    files: int
    lines: int
    languages: dict[str, int]  # language → files
    primary: str | None
    manifests: list[str]
    has_tests: bool
    has_ci: bool
    sensitive_paths: list[str]
    size: str  # small / medium / large
    kind: str  # library / service / web / mixed / docs
    state: str  # greenfield / active / legacy
    proposed_gates: dict[str, list[str]]
    proposed_routing_notes: list[str]
    proposed_privacy_rule: str
    recommendations: list[str] = Field(default_factory=list)


def scan(root: Path, max_files: int = 20_000) -> Analysis:
    langs: Counter[str] = Counter()
    files = lines = 0
    sensitive: list[str] = []
    has_tests = has_ci = False
    manifests: list[str] = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_dir():
            if rel.parts and rel.parts[0] == ".github" and (p / "workflows").is_dir():
                has_ci = True
            continue
        files += 1
        if files > max_files:
            break
        if p.name in MANIFESTS:
            manifests.append(rel.as_posix())
        low = rel.as_posix().lower()
        if any(s in low for s in SENSITIVE) and p.suffix.lower() not in (".md",):
            sensitive.append(rel.as_posix())
        if "test" in low:
            has_tests = True
        if rel.parts and rel.parts[0] in (".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"):
            has_ci = True
        lang = LANG_EXT.get(p.suffix.lower())
        if lang:
            langs[lang] += 1
            try:
                lines += sum(1 for _ in p.open("rb"))
            except OSError:
                pass
    code_langs = {k: v for k, v in langs.items() if k not in ("markdown", "html", "css", "sql")}
    primary = max(code_langs, key=lambda k: code_langs[k]) if code_langs else None
    size = "small" if lines < 5_000 else "medium" if lines < 50_000 else "large"
    if not code_langs:
        kind = "docs"
    elif langs.get("html", 0) + langs.get("css", 0) > sum(code_langs.values()):
        kind = "web"
    elif any(m.endswith("package.json") for m in manifests) and primary in (
        "typescript",
        "javascript",
    ):
        kind = "web"
    elif primary and files > 0:
        kind = (
            "service"
            if any(
                "api" in s.lower() or "server" in s.lower()
                for s in (str(x) for x in root.glob("*"))
            )
            else "library"
        )
    else:
        kind = "mixed"
    if files < 20:
        state = "greenfield"
    elif not has_tests and size != "small":
        state = "legacy"
    else:
        state = "active"
    gates = GATES.get(primary or "", {"before_review": [], "after_merge": []})
    notes = []
    recs = []
    if state == "legacy":
        recs.append(
            "legacy without tests: first wave = characterisation tests (role review/implement on "
            "antigravity + local); refactors only after green tests (playbook legacy-modernize)"
        )
    if state == "greenfield":
        recs.append(
            "greenfield: contract-first — Claude writes interfaces/contracts before any "
            "implement card"
        )
    if sensitive:
        recs.append(
            f"{len(sensitive)} sensitive-looking path(s): plan cards touching them as "
            "privacy=internal; "
            "extend never_share if they hold secrets"
        )
    if kind == "web":
        notes.append("UI cards → antigravity/copilot (role implement, assets for graphics)")
    if not has_ci:
        recs.append(
            "no CI detected: add a workflow running the same gates so merges are checked twice"
        )
    if not has_tests:
        recs.append(
            "no tests detected: reviewer must run acceptance commands manually; "
            "consider a test card first"
        )
    privacy_rule = (
        "internal when scope/context touches: "
        + ", ".join(sorted({s.split("/")[0] for s in sensitive})[:8])
        if sensitive
        else "public by default; use internal for config and credentials-adjacent paths"
    )
    return Analysis(
        files=files,
        lines=lines,
        languages=dict(langs.most_common()),
        primary=primary,
        manifests=manifests,
        has_tests=has_tests,
        has_ci=has_ci,
        sensitive_paths=sensitive[:50],
        size=size,
        kind=kind,
        state=state,
        proposed_gates=gates,
        proposed_routing_notes=notes,
        proposed_privacy_rule=privacy_rule,
        recommendations=recs,
    )


def render(a: Analysis, name: str) -> str:
    langs = ", ".join(f"{k} {v}" for k, v in a.languages.items()) or "-"
    lines = [
        f"# Council analysis — {name}",
        "",
        f"Files {a.files}, lines {a.lines}, size **{a.size}**, kind **{a.kind}**, "
        f"state **{a.state}**.",
        f"Languages: {langs}. Primary: {a.primary or '-'}. "
        f"Manifests: {', '.join(a.manifests) or '-'}.",
        f"Tests: {'yes' if a.has_tests else 'no'}. CI: {'yes' if a.has_ci else 'no'}.",
        "",
        "## Proposed gates (council.json → gates)",
        "```json",
        '{"before_review": ' + str(a.proposed_gates["before_review"]).replace("'", '"') + ",",
        ' "after_merge": ' + str(a.proposed_gates["after_merge"]).replace("'", '"') + "}",
        "```",
        "",
        "## Privacy",
        a.proposed_privacy_rule,
        "",
    ]
    if a.sensitive_paths:
        lines += ["Sensitive-looking paths:"] + [f"- `{p}`" for p in a.sensitive_paths[:20]] + [""]
    if a.proposed_routing_notes:
        lines += ["## Routing notes"] + [f"- {n}" for n in a.proposed_routing_notes] + [""]
    if a.recommendations:
        lines += ["## Recommendations"] + [f"- {r}" for r in a.recommendations] + [""]
    return "\n".join(lines)
