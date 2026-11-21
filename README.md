# ui-review

Visual evidence for agent-made UI changes, judged from a phone.

A run has one of two modes. In a compare run, an agent replays one recipe on the build saved at task start and on the current build, back to back, on the same simulator; `uireview` decides which side is which from the installed app's content hash. In a screens run there is no before side: each card is one state the owner judges on its own (a Gate 1 prototype, a new screen), shot from a recipe or while the agent drives the simulator. Either way `uireview` takes the screenshots, crops the regions the agent points at, and publishes the run to a fixed web shell. The owner opens the site over the tailnet, taps through the cards, and leaves ✅ / ❌ / ❓ per card. Verdicts live on the server, so the phone and the laptop see the same state; the agent reads them back with `uireview verdict`.

The agent never writes HTML or picks image files. It fills captions in `notes.json` that reference cards by id; everything else is produced and checked by the tool.

Design and the reasons behind each choice: [docs/plan.md](docs/plan.md) (Chinese).

## Requirements

A macOS host on the tailnet that runs the iOS simulators, with:

- `python3` ≥ 3.9 (stdlib only)
- ImageMagick 7 (`magick`)
- `ffmpeg` / `ffprobe` with libx264 (recordings)
- Xcode command line tools (`xcrun simctl`)
- [`sim-use`](https://github.com/lycorp-jp/sim-use) for accessibility snapshots
- `trash` (macOS 15+ ships `/usr/bin/trash`)
- Tailscale with `tailscale serve`

## Install

```sh
./uireview install   # ~/.local/bin/uireview symlink, LaunchAgent com.ohlulu.ui-review, tailscale serve :8787 → 127.0.0.1:8788
uireview doctor      # every line should be ✅
pi install /path/to/ui-review   # agent skill: adds this repo as a local pi package
```

The repo is a pi package by convention: pi loads `skills/ui-review/SKILL.md` from the checkout in place, so a `git pull` updates the skill. `pi install` writes the path relative to `~/.pi/agent/settings.json`; a machine without the checkout skips the entry silently.

The server is a LaunchAgent (`RunAtLoad` + `KeepAlive`): it restarts if it dies and comes back after login. It is not reachable before someone logs in after a reboot. The site is tailnet-only (`tailscale serve`, never Funnel); the LAN address refuses connections. Logs: `~/.local/state/ui-review/logs/serve.log`.

## Agent workflow

Compare run:

```sh
# 1. task start: clone the current build as the baseline (APFS clone, ~0.05 s)
uireview base save --project myapp --app path/to/App.app --repo path/to/checkout

# 2. task end: replay one recipe on base and current build
uireview capture --project myapp --udid <sim> --bundle com.example.app \
  --app path/to/App.app --recipe review.sh --rotate 270 --title "Product detail layout"
#    → prints rN and the notes.json path

# 3. fill ~/.local/state/ui-review/work/rN/notes.json (text only), then
uireview publish rN          # validates, builds webp + ROI crops, prints the URL (exit 1 if the site is unreachable)

# 4. after the owner says "rN 看完"
uireview verdict rN
```

`capture` refuses to run when the project has no saved base, so a forgotten base fails instead of quietly dropping the before side. `--no-base` asks for a screens run on purpose: the recipe runs on the current build only. `--round-of rM` marks the new run as a rework of `rM`, which then counts as decided.

Screens run, shot while driving the simulator:

```sh
# the app is already built, installed and launched the way the project launches it
uireview start --project myapp --udid <sim> --bundle com.example.app --rotate 270 --title "Show filter prototype"
#    → prints rN; the installed build's hash is the run's build
uireview shot filter-menu --run rN --label "Sort menu with the Show section"   # after driving to that state
uireview shot filter-on --run rN --label "Not for sale selected"
# fill notes.json (each shot appended a card), then
uireview publish rN
```

`shot --run` and `clip --run` accept only runs opened by `start`, always shoot the after side, and refuse once the installed app's hash differs from the one `start` recorded — rebuild, then `start` a new run. A shot pixel-identical to an earlier one on the same side prints a warning.

Other commands: `clip` (see below), `list`, `close rN [--reopen]`, `prune [--dry-run]`, `serve`, `doctor`. Each has `-h`.

### Recipes

A recipe is a bash script `capture` runs once per side, with these variables set: `UIREVIEW_RUN`, `UIREVIEW_SIDE` (`before` / `after`), `UIREVIEW_UDID`, `UIREVIEW_BUNDLE`, `UIREVIEW_ROOT`. It launches the app with fixed launch arguments, navigates, and calls `uireview shot <slug> --label "Title"` for each card. `shot` keeps taking frames until two consecutive ones are pixel-identical (otherwise the card is marked `UNSTABLE`) and saves the accessibility tree next to it.

- Wait for an accessibility id that exists only on the target screen before each `shot`. Waiting for a sidebar item that is always present lets the recipe shoot the same screen four times; `capture` warns when two cards on one side are pixel-identical.
- `sim-use` assumes landscape-right when it cannot read the orientation, so rotate the simulator first (`sim-use ios rotate landscape-right --device <udid>`) or taps land in the wrong place.
- A landscape-right iPad screenshot comes out portrait; pass `--rotate 270`.
- Never reinstall or rebuild the app inside a recipe (no `make run`, no `simctl install`): `shot` and `clip` check that the installed app's hash is that side's build and refuse otherwise; `capture` installs each side itself.
- `capture` sets the status bar to 09:41 and clears it afterwards, and reinstalls the after build if a recipe dies mid-way (verifying its hash).

### Recordings

Record only when the change is about motion or timing — animation, transition, gesture, loading, toast, keyboard avoidance. Static layout and copy changes get screenshots only. At most 3 clips per run.

```sh
uireview clip menu-open --label "Open menu" -- sim-use tap '#menu.button'
uireview shot menu-open --label "Menu open"     # every clip belongs to a card with the same slug
```

`clip` wraps the whole recording, so a recipe never handles a recorder pid:

1. Stops any recorder left on this simulator.
2. Starts `simctl io recordVideo` and waits for its documented `Recording started` line (10 s limit), then 0.3 s of stillness.
3. Runs the command (`--timeout`, default 20 s), then keeps recording `--settle` seconds (default 1).
4. Sends SIGINT and waits 10 s; sends SIGINT again; only then SIGKILL. A killed recorder marks the clip `needs_reboot` and fails only that card's video — reboot the simulator before recording again.
5. Does the same stop sequence when the wrapper itself gets SIGTERM / SIGHUP (exit 130).
6. Re-encodes at 1× speed: CFR 60, 1280 wide, h264 CRF 24, faststart, no audio, rotated like the screenshots. The raw recording is not kept.

`clip` exits with the command's exit code, so `set -e` recipes stop when the action fails. `publish` stacks before above after into one mp4, padding the shorter side with its last frame; the site plays it inline with 1× / 0.5× / 0.25×. Both sides start recording at the same point in the recipe, but the app's reaction time can differ by a few hundred milliseconds between builds.

### notes.json

`capture` writes a skeleton; in a run opened by `start`, each `shot` appends its card and keeps what is already filled. Keep card ids and names in order; fill only these fields:

| Field | Level | Meaning |
|---|---|---|
| `title` | run | Headline on the site |
| `judge` | run | What the owner needs to decide |
| `checks` | run | Strings shown as "agent reported" (tests, flows run) |
| `what` | card | What changed (compare) or what this state is (screens) — required on every card except `UNCHANGED` |
| `look` | card | Up to 3 places to look |
| `question` | card | Optional question for this card |
| `roi` | card | Optional, empty by default; only for a change too small to see in the full screenshot at phone width. Regions to show at 1:1: `{"id": "<accessibility id>", "nth": 0}` or `{"rect": [x, y, w, h]}` in points, each with an optional `label` |

`publish` fails on unknown keys, a missing `what`, non-string text fields, cards out of order, an ROI found on neither side, or any screenshot whose sha256 changed since capture. The ROI crop is the union of both sides' frames plus 12 pt, applied identically to both sides.

Card status comes from a pixel comparison (`magick compare -fuzz 1%`): `CHANGED`, `UNCHANGED` (collapsed on the site), `NEW` (no before shot in a compare run), `MISSING AFTER`, and `MOTION` — identical end states on a card that has a recording, which still needs a caption and a verdict. Every card of a screens run is `SCREEN`: no comparison, shown without a tag, and it needs a caption and a verdict. A run whose cards are all `UNCHANGED` needs no verdict and is decided on publish. `publish` also rejects a clip without a matching shot and any clip whose sha256 changed.

## Site

The shell is light-only, set in Geist (Latin, served from `web/geist.woff2`, OFL in `web/geist-OFL.txt`) with PingFang TC for Chinese, and uses Phosphor icons inlined in `web/app.js`. Run ids are lowercase on disk, in URLs and in CLI output (`r18`); the site shows them uppercase (`R18`), like card ids, and every command and `--round-of` accepts either case.

- `/` — each row leads with its run id at title size; pending runs newest first with how many cards still need a verdict (Stale after 14 days, with a close button), decided runs with their outcome (全部通過 / n 張要改 / 已關閉 / 無變更), project filter when there is more than one project.
- `/#rN` — run page; `/#rN/C02` jumps to a card. The header carries the run's `judge` question, notices (closed, superseded, rework, A/A), and the agent's `checks` folded away; build hashes sit in 技術細節 at the bottom. In a compare run, a Before / After switch above each screenshot swaps the two sides instantly, with no transition, so small differences blink; a screens run shows the single screenshot under its caption. A tap on a screenshot or ROI crop opens a full-screen viewer: a tap on the image there swaps Before / After (mirrored back to the card), ← / → or the bottom buttons step through the run's images (collapsed Unchanged cards are skipped), and ✕, Esc, or a tap outside the image closes it. Closing the run from its page returns to the list; reopening stays on the run. Verdict buttons (通過 ✅ / 要改 ❌ / 有疑問 ❓) and notes save to the server; "已儲存" appears only after the server acknowledges. Below the last card, 全部通過 marks every card that still needs a verdict and has no mark yet as ✅ in one save; cards already marked ❌ or ❓ keep their mark. If another device changed the run meanwhile (409), the page loads the newer state and asks for the tap again.
- API: `GET /api/runs`, `GET|POST /api/runs/<id>/verdict` (`{"rev": n, "cards": {"C01": {"v": "✅", "note": ""}}, "closed": bool}`; requires `Content-Type: application/json` and `X-UIReview: 1`, same-origin, ≤ 8 KB, typed fields), `GET /runs/<id>/<file>` with byte ranges (iOS Safari needs 206 for mp4), `GET /healthz`. Every route except `/healthz` answers only to a known `Host` — `127.0.0.1` / `localhost` on the server port and the tailnet name on 8787 — so a DNS-rebound page cannot read or write runs; HTML refuses to be framed.
- Each run carries `manifest.json` with `schema: 2` and `mode` (`compare` / `screens`). The shell shows "不支援" for any other schema; there is no compatibility layer. A card may carry `"video": {"src": "C01.mp4", "sides": ["before", "after"]}` — one h264 mp4, before stacked above after when both sides recorded — and `"video_error"` when a recording failed.

## Retention

Runs on every `publish`; `uireview prune --dry-run` shows the plan. Everything goes to the Trash, so space returns only when the Trash is emptied.

| What | When |
|---|---|
| Decided run (every non-unchanged card ✅ / ❌, closed, or superseded) | 7 days after the decision |
| Pending run | Never; STALE after 14 days |
| Raw shots `work/rN` | When the run is decided |
| Unpublished capture | After 3 days |
| Base `.app` | With the last run that used it, or after 14 days unused |

## State layout

```
~/.local/state/ui-review/        (override with UIREVIEW_ROOT; `install` passes it to the LaunchAgent)
  base/<project>-<time>/          base.json + app/<Name>.app
  work/rN/                        capture.json (tool-owned), notes.json (agent), recipe.sh (capture only), shots/<side>/<slug>.png + .ax.json, clips/<side>/<slug>.mp4
  runs/rN/                        manifest.json, verdict.json, webp / mp4 assets
  logs/serve.log  counter  config.json
```

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests use a temporary `UIREVIEW_ROOT`, an in-process server on a free port, and a fake recorder script in place of `simctl io recordVideo` (including one that ignores SIGINT); the publish and clip tests skip without `magick` / `ffmpeg`. The web shell has no build step — edit `web/` and reload.

## License

[MIT](LICENSE). The bundled Geist font is under the SIL Open Font License ([web/geist-OFL.txt](web/geist-OFL.txt)).
