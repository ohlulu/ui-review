---
name: ui-review
description: >-
  Use when the owner should look at iOS simulator screens from his phone — a UI change that needs before/after evidence, Gate 1 prototype states, a new screen or state to judge on its own, or screenshots you are about to cite by file name or number in a report — or when the owner says a review run is done. NOT for code review. Trigger words: "ui-review", "uireview", "before/after", "visual evidence", "Gate 1", "視覺證據", "截圖比對", "前後對照", "給我看畫面", "截圖給我看", "請看截圖", "手機上看", "r7 看完", "錄影比對".
---

# ui-review — visual evidence the owner judges from his phone

`uireview` publishes simulator screenshots as cards on a private site (port 8787 on the host's tailnet name, tailnet only; `uireview publish` prints the exact URL). Each card carries your caption and what to look at next to the image, and the owner marks it ✅ / ❌ / ❓ from his phone; verdicts live on the server. You write captions only — the tool owns screenshots, recordings, statuses, and the page.

`uireview` exists only on the host that runs the site. If `command -v uireview` fails, you are on another machine: tell the owner the review has to run on that host instead of improvising screenshots.

Full reference: `README.md` at the root of this repo (two levels above this file); per-command help: `uireview <command> -h`.

## When to use

- You are about to ask the owner to look at screenshots. A report that cites `03.png` or "see screenshot 04" makes him scroll a terminal, and on the phone he cannot see the image at all; publish the states and link the cards instead.
- The owner says "rN 看完" (or asks what he decided on a run). The site shows ids uppercase (R12) and every command accepts either case.

Not for: code review (`/review`, `review_plan`), logic-only changes with no visible effect.

If the project documents its own review adapter (its `AGENTS.md` or verify skill), use that; it wraps these commands with the project's simulator, bundle id, and launch arguments. Never drive a simulator another agent has pinned — check the project's rules first.

## Pick the mode

- **compare** — the same recipe replayed on the build saved at task start and on the current build; the owner flips Before / After. Use it when the owner should judge the change against today's look. It needs `uireview base save` before the first UI edit; a base saved later already contains part of the change.
- **screens** — after only; each card is a state judged on its own. Use it when only the new state matters (a Gate 1 prototype, a new screen, states reached while verifying) or when no base was saved. A Gate 1 capture is a design target, never a base. Never substitute older screenshots for a missing base: a different fixture or clock makes the pair lie.

`capture` refuses to run without a base unless you pass `--no-base`, so a forgotten base fails loudly instead of quietly turning into a screens run.

## Compare workflow

1. **Task start, before touching UI:** build once and save the baseline.
   `uireview base save --project <p> --app <path/App.app> --repo <checkout>`
2. **Write a recipe** — a bash script that launches the app with fixed launch arguments, navigates, and calls `uireview shot <slug> --label "Title"` per card. Rules below.
3. **Task end, after the final build:**
   `uireview capture --project <p> --udid <sim> --bundle <id> --app <path/App.app> --recipe <script> --rotate <deg> --title "<change>"`
   It installs base, runs the recipe, installs the current build, runs it again, and prints `rN` plus the `notes.json` path. Read its warnings before going on.
4. Fill notes and publish (below).

## Screens workflow

Either replay a recipe on the current build only — `uireview capture … --no-base` — or shoot while you drive:

1. Build, install, and launch the app the way the project's verify skill says, then open the run:
   `uireview start --project <p> --udid <sim> --bundle <id> --rotate <deg> --title "<what to judge>"`
   It records the installed build's hash and prints `rN`.
2. Drive the simulator to each state and take it: `uireview shot <slug> --run rN --label "Title"`, one card per state. Each shot appends a card to `notes.json`. For motion, record a clip first (see Recordings).
3. Rebuilding or reinstalling the app mid-run makes every later `shot` refuse; open a new run with `start` for the new build.
4. Fill notes and publish (below).

## Notes, publish, verdicts

1. **Fill `~/.local/state/ui-review/work/rN/notes.json`** (text only, keep card ids and order). The owner reads cards in Traditional Chinese: write the run `--title`, every `--label`, and all `notes.json` text in 繁體中文 (Taiwan), whatever language the app on screen shows — the screenshots may stay in English.
   - `judge`: the one decision you need from the owner.
   - `checks`: tests and flows you ran, as plain strings.
   - per card `what`: compare — the concrete change ("price column ends at 907 pt, badge starts at 919 pt"); screens — what state this is and what decides whether it is right. Required on every card except `UNCHANGED`.
   - per card `look` (≤ 3 places) and an optional `question`.
   - per card `roi`: leave it `[]`; the full screenshot plus `what` and `look` is what the owner judges from. Add a region only when the change is too small to see in the full screenshot at phone width — a shift under about 10 pt, a hairline, a single glyph or icon: `{"id": "<accessibility id>", "label": "…"}` for a 1:1 crop, `{"rect": [x, y, w, h]}` in points only when the element has no id.
2. **`uireview publish rN`** prints the URL. Reply with the URL and the `judge` line; point at a card as `<url>/#rN/C02`, never at a screenshot file. If it exits 1 because the site is unreachable, run `uireview doctor` and fix that before handing out the link.
3. **When the owner says "rN 看完":** `uireview verdict rN`. Act on every ❌ note and answer every ❓. A rework is a fresh run with `--round-of rN` (on `capture` or `start`); the old run then counts as decided.

## Recipe rules

- Never reinstall or rebuild the app inside a recipe (`make run`, `simctl install`, a launch helper that builds): `shot` and `clip` refuse when the installed app is not that side's build.
- Before each `shot`, wait for an accessibility id that exists only on the target screen. A sidebar item is present on every screen, so waiting on it shoots the same screen again; `shot` warns when a screenshot is pixel-identical to an earlier one on the same side — treat that as a broken recipe (or, in a screens run, a state you did not reach).
- Rotate an iPad simulator to landscape-right first (`sim-use ios rotate landscape-right --device <udid>`): `sim-use` assumes landscape-right when it cannot read the orientation, so any other orientation sends taps to the wrong place. Landscape-right screenshots come out portrait; pass `--rotate 270`.
- Seed data through launch arguments so both builds start from identical fixtures; a pair whose fixtures differ (stock untracked vs 34 in stock) shows differences the change did not make.
- `set -euo pipefail`; the recipe's environment carries `UIREVIEW_UDID` and `UIREVIEW_BUNDLE`.

## Recordings

Record only motion or timing changes — animation, transition, gesture, loading, toast, keyboard avoidance. Static layout and copy get screenshots only. At most 3 clips per run.

```sh
uireview clip menu-open --label "Open menu" -- sim-use tap '#menu.button'
uireview shot menu-open --label "Menu open"    # same slug: the clip belongs to this card
```

`publish` refuses a clip without a same-slug `shot`. In a run opened with `start`, add `--run rN` to both.

`clip` owns the recorder (handshake, bounded SIGINT stop, re-encode) and exits with the command's exit code. If it reports `needs_reboot`, reboot the simulator (`xcrun simctl shutdown <udid> && xcrun simctl boot <udid>`) before recording again — the recorder hung inside the simulator.

## Reading the result

- `UNCHANGED` (pixel-identical within 1 %) needs no verdict; a run with only unchanged cards is decided on publish. Seeing it where you expected a change means the recipe did not reach the changed state, not that the change is invisible.
- `MOTION` means identical end states on a recorded card; it still needs `what` and a verdict.
- `SCREEN` is every card of a screens run; it needs `what` and a verdict.
- `capture` noting "same build (A/A)" means base and current build are identical — every card should be `UNCHANGED`.
- `publish` refuses edited screenshots or clips, unknown keys, and missing `what`. Fix the notes or re-run the capture; never edit files under `shots/` or `clips/`.

## Quick reference

```
uireview base save --project P --app App.app [--repo DIR]
uireview capture --project P --udid U --bundle B --app App.app --recipe R --title T [--rotate 270] [--round-of rN] [--no-base]
uireview start --project P --udid U --bundle B --title T [--rotate 270] [--round-of rN]   # screens run, shoot while driving
uireview shot <slug> [--run rN] [--label L]                 # in a recipe, or --run on a started run
uireview clip <slug> [--run rN] [--label L] -- <command…>   # same
uireview publish rN | verdict rN | close rN | list | prune --dry-run | doctor
```
