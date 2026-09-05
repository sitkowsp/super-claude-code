# Recipes and playbooks

A playbook is how Claude splits work when it decides. Shipped ones live in `playbooks/`; put your
own in `.council/playbooks/<name>.json` (same name overrides). Selection is keyword-based and the
planner tells you why (`council_playbooks(goal)`); `/council:plan --playbook <name>` forces one.

## `feature` (default) — a new feature in an existing app

Wave 1 (Claude): write the change contract — what changes in API/model/UI, what must not.
Wave 2 (parallel): `implement` backend → Codex; `implement` UI (disjoint scope) → Antigravity or
Copilot; `docs` → Copilot. Wave 3: `review` second opinion when the diff is large; Claude glues
and merges. Prefer `depends_on` over shared files.

## `bug-hunt` — a bug nobody can see

Do not split work, split hypotheses. Claude writes a minimal repro and 3 hypotheses;
`/council:compare` sends the same repro to 2–3 models, each confirms/refutes one and proposes a
fix **without implementing**. Claude picks and implements the fix (bug fixes are small and
entangled) plus a regression test. Use `local` if the repro needs company data.

## `data-internal` — a report on company data

Everything `local-only`. Claude writes the field/rule spec without data; `local` (Ollama) runs the
SQL/extraction in its workdir and reports aggregates only; if the result becomes code, a second
wave like `feature` with no data in scope. `never_share` must cover dumps and `*.sql`.

## Graphics (`assets` role)

Icons, logos, buttons, illustrations, diagrams. SVG/CSS from any executor; PNG/JPG from Codex or
Antigravity (built-in image tools on your subscriptions). Put the target file names in `scope`
and say the sizes in `goal`; the prompt already tells the executor to copy generated files into
the workdir and check their size. Review `done_without_changes` carefully for this role.

## Second opinion on your own work

```
/council:ask local "review this diff for bugs" --files src/x.py
/council:compare "is approach A or B better for ...?" --models codex,antigravity
```

Local Ollama first: free tokens, good enough for a sanity check.

## A model on probation

New models start on `probation`: cards ≤ 150 changed lines, a second opinion is mandatory, merge
only after review. Three first-pass approvals promote it. If something merged turns out broken:

```
/council:defect T-012 "export breaks on empty list" --lesson "codex: guard empty iterables in exports"
```

The lesson lands in that model's next TASK.md for the same role.

## Session hygiene

`/council:status` each time you come back; `/council:why T-007` when a decision looks odd;
`/council:handoff` before you stop. Reports are the executor's claims — the reviewer runs the
acceptance commands itself.
