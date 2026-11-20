# AGENTS.md — ui-review

Read `README.md` for usage and `docs/plan.md` (Chinese) for the design and why each choice was made.

## Hard rules

- `uireview` stays one stdlib-only Python file: `install` symlinks it into `~/.local/bin`, and the LaunchAgent runs it with whatever `python3` is on `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`. Keep it runnable on Python 3.9.
- `web/` is a fixed, no-build shell. Agents using the tool never write HTML; new presentation goes into `web/app.js` driven by manifest fields.
- A manifest format change bumps `SCHEMA` in `uireview` and `web/app.js` together. No compatibility layer: old runs show "unsupported" and age out under retention.
- The agent-facing contract is `notes.json` text plus card ids. Never let notes reference file paths, and never let anything but `uireview shot` produce a screenshot that `publish` accepts.
- Deletes go through `trash`, never `rm` / `shutil.rmtree` on state outside a staging dir the tool just created.
- The server binds `127.0.0.1` only and is exposed through `tailscale serve`. Never Funnel, never `0.0.0.0`.

## Working here

- Tests: `python3 -m unittest discover -s tests -v`. They set `UIREVIEW_ROOT` to a temp dir; never point a test at `~/.local/state/ui-review`.
- After changing the server or `web/`, the running LaunchAgent picks up `web/` edits on reload, but Python changes need `launchctl kickstart -k gui/$(id -u)/com.ohlulu.ui-review`. Then `uireview doctor`.
- Check the shell in a phone-sized browser (e.g. `agent-browser --session uir set device "iPhone 14"`) before asking the owner to look on the iPhone.
- Simulator work for acceptance runs uses its own simulator, not another project's pinned one, unless that project's owner says it is free.
- The agent-facing guide is `skills/ui-review/SKILL.md`. This repo is a local pi package (`pi install <checkout>` adds it to `~/.pi/agent/settings.json`), so the skill loads in every project on a machine that has the checkout and nowhere else. Do not copy it into `~/.pi/agent/skills/`. A change to a command, flag, notes.json field, or card status updates that skill and `README.md` in the same task.
- Commits follow Conventional Commits.
- `.pi/settings.json` opts this repo into the UI design and animation skills (`ui-design-principles` plus the web subset of `emilkowalski/skills`) through `~/` paths. That is the intended idiom, not an environment leak: pi expands `~` per machine and silently skips a path that does not exist, so do not rewrite them as absolute paths or remove them.
