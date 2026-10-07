Manhaj (مَنْهَج): Arabic review and analysis workspace built on one book. The full agent guide is AGENTS.md, imported below.

@AGENTS.md

## Claude-specific

- Talk to the owner in plain language (they are not a developer and often write in Gulf Arabic). Show the plan before large changes; keep user-facing wording Arabic, plain, English digits, no em dashes.
- UI checks: when the Python server cannot start on this machine (Windows Application Control), use the static harness described in AGENTS.md ("Testing the UI without the Python server") through the Browser pane: serve the copied `web/` with `python -m http.server`, inject the fetch mock, then measure. Copy the files again after every edit to `web/`.
- In a hidden or minimized Browser pane, finish animations and disable transitions before measuring layout, or the numbers will be wrong.
- Database changes: if `npx supabase` cannot run, use the Supabase MCP `apply_migration`, then rename the repo migration file to the version `list_migrations` reports. Use MCP SQL for reads only; never write test data to production.
- Deploys: after a merge to `main`, confirm a production deployment exists for the merge commit with the Vercel MCP. If the webhook missed it, create one from GitHub source (`main` + the commit sha) with the Vercel MCP.
- If merging a PR is blocked by permissions, open the PR, get CI green and the preview built, then ask the owner to merge.
- Images: generate with the owner's image MCP (Slide Assets), save under a NEW filename in `web/img/`, and list it in `web/img/README.md`.
- Never read `.env*`, `work/` or token files, and never print secrets in chat.
