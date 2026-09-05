# Lessons

One line per review_reject / dissent / defect: `- [model/role] rule`.

- [copilot/docs] Copy-paste social copy (Facebook/Instagram/LinkedIn): one paragraph = one line, never hard-wrap, and no markdown (backticks, bold) inside the post body — platforms show it literally.
- [codex/assets] For HTML-rendered social graphics, editing the source and re-rendering with headless Edge from the workdir works; verify PNG IHDR size after render.
- [codex/assets] Headless Edge from the Codex workdir is unreliable (worked in T-001, failed in T-003 with 'GPU process isn't usable'): try once with --disable-gpu; if it fails, report blocked instead of retrying, and never put the browser profile dir inside the workdir — the chair re-renders the PNGs after merge.
