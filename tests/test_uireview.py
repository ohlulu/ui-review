"""Tests for the uireview CLI. Run: python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "uireview"
loader = importlib.machinery.SourceFileLoader("uireview", str(SCRIPT))
spec = importlib.util.spec_from_loader("uireview", loader)
ur = importlib.util.module_from_spec(spec)
loader.exec_module(ur)

DAY = ur.DAY
HAS_MAGICK = shutil.which("magick") is not None


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = unittest.mock.patch.dict(os.environ, {"UIREVIEW_ROOT": self.tmp.name, "UIREVIEW_URL": "http://test:8787"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def publish_run(self, run_id: str, statuses: list[str], verdict: dict | None = None, published: float | None = None,
                    base: str | None = None) -> Path:
        folder = ur.sub("runs") / run_id
        cards = [{"id": f"C{i:02d}", "name": f"card-{i}", "status": s} for i, s in enumerate(statuses, 1)]
        ur.write_json(folder / "manifest.json", {
            "schema": ur.SCHEMA, "run": run_id, "project": "demo", "title": run_id, "created": published or ur.now(),
            "published": published or ur.now(), "base": {"id": base, "hash": "h", "git": {}} if base else None, "cards": cards})
        if verdict is not None:
            ur.write_json(folder / "verdict.json", {**ur.empty_verdict(), **verdict})
        return folder



class ParseRange(unittest.TestCase):
    def test_no_header_or_unsupported_forms_serve_whole_body(self) -> None:
        self.assertIsNone(ur.parse_range(None, 10))
        self.assertIsNone(ur.parse_range("items=0-1", 10))
        self.assertIsNone(ur.parse_range("bytes=0-1,4-5", 10))
        self.assertIsNone(ur.parse_range("bytes=-", 10))

    def test_single_ranges(self) -> None:
        self.assertEqual(ur.parse_range("bytes=0-1", 10), (0, 1))
        self.assertEqual(ur.parse_range("bytes=5-", 10), (5, 9))
        self.assertEqual(ur.parse_range("bytes=-3", 10), (7, 9))
        self.assertEqual(ur.parse_range("bytes=-30", 10), (0, 9))
        self.assertEqual(ur.parse_range("bytes=8-100", 10), (8, 9))

    def test_unsatisfiable(self) -> None:
        for header in ("bytes=10-", "bytes=5-2", "bytes=-0"):
            with self.subTest(header=header), self.assertRaises(ValueError):
                ur.parse_range(header, 10)


class ValidateNotes(unittest.TestCase):
    capture = {"title": "t", "shots": [
        {"name": "home", "side": "after"}, {"name": "home", "side": "before"},
        {"name": "detail", "side": "after"}]}

    def notes(self) -> dict:
        return ur.skeleton(self.capture)

    def test_skeleton_order_follows_after_side(self) -> None:
        self.assertEqual([(c["id"], c["name"]) for c in self.notes()["cards"]], [("C01", "home"), ("C02", "detail")])

    def test_unchanged_cards_need_no_caption(self) -> None:
        self.assertEqual(ur.validate_notes(self.notes(), self.capture, {"home": "UNCHANGED", "detail": "UNCHANGED"}), [])

    def test_changed_and_new_cards_need_what(self) -> None:
        errors = ur.validate_notes(self.notes(), self.capture, {"home": "CHANGED", "detail": "NEW"})
        self.assertEqual(len(errors), 2)
        notes = self.notes()
        notes["cards"][0]["what"] = "moved the button"
        notes["cards"][1]["what"] = "new screen"
        self.assertEqual(ur.validate_notes(notes, self.capture, {"home": "CHANGED", "detail": "NEW"}), [])

    def test_rejects_unknown_keys_paths_and_reordering(self) -> None:
        statuses = {"home": "UNCHANGED", "detail": "UNCHANGED"}
        notes = self.notes()
        notes["cards"][0]["image"] = "/tmp/old.png"
        self.assertIn("unknown keys", " ".join(ur.validate_notes(notes, self.capture, statuses)))
        notes = self.notes()
        notes["summary"] = "x"
        self.assertIn("unknown run keys", " ".join(ur.validate_notes(notes, self.capture, statuses)))
        notes = self.notes()
        notes["cards"].reverse()
        self.assertIn("keep the ids and names", " ".join(ur.validate_notes(notes, self.capture, statuses)))

    def test_roi_shape(self) -> None:
        statuses = {"home": "UNCHANGED", "detail": "UNCHANGED"}
        for roi, ok in (({"id": "a.b"}, True), ({"rect": [0, 0, 10, 10]}, True), ({"id": "a", "rect": [0, 0, 1, 1]}, False),
                        ({"rect": [0, 0, 1]}, False), ({"label": "x"}, False), ({"id": "a", "path": "/x"}, False)):
            notes = self.notes()
            notes["cards"][0]["roi"] = [roi]
            with self.subTest(roi=roi):
                self.assertEqual(ur.validate_notes(notes, self.capture, statuses) == [], ok)

    def test_text_fields_must_be_strings(self) -> None:
        notes = self.notes()
        notes["cards"][0]["what"] = None
        notes["cards"][1]["look"] = [1]
        errors = ur.validate_notes(notes, self.capture, {"home": "CHANGED", "detail": "NEW"})
        self.assertTrue(any("C01: `what` must be strings" in e for e in errors), errors)
        self.assertTrue(any("C02: `look`" in e for e in errors), errors)

    def test_look_is_capped(self) -> None:
        notes = self.notes()
        notes["cards"][0]["look"] = ["a", "b", "c", "d"]
        self.assertTrue(ur.validate_notes(notes, self.capture, {"home": "UNCHANGED", "detail": "UNCHANGED"}))


class DuplicateScreens(unittest.TestCase):
    def test_flags_identical_shots_on_one_side_only(self) -> None:
        shots = [{"side": "before", "name": "a", "sha256": "x"}, {"side": "before", "name": "b", "sha256": "x"},
                 {"side": "after", "name": "a", "sha256": "x"}, {"side": "after", "name": "b", "sha256": "y"}]
        self.assertEqual(ur.duplicate_screens({"shots": shots}), ["before: a and b are pixel-identical"])


class Decided(Base):
    def manifest(self) -> dict:
        return {"run": "r1", "project": "p", "title": "t", "created": ur.now(), "published": ur.now(),
                "cards": [{"id": "C01", "status": "CHANGED"}, {"id": "C02", "status": "UNCHANGED"}]}

    def test_needs_thumbs_on_every_non_unchanged_card(self) -> None:
        m = self.manifest()
        self.assertFalse(ur.is_decided(m, ur.empty_verdict()))
        self.assertFalse(ur.is_decided(m, {**ur.empty_verdict(), "cards": {"C01": {"v": "❓"}}}))
        self.assertTrue(ur.is_decided(m, {**ur.empty_verdict(), "cards": {"C01": {"v": "❌"}}}))

    def test_closed_or_superseded_is_decided(self) -> None:
        self.assertTrue(ur.is_decided(self.manifest(), {**ur.empty_verdict(), "closed": True}))
        self.assertTrue(ur.is_decided(self.manifest(), {**ur.empty_verdict(), "superseded_by": "r2"}))

    def test_summary_counts_and_stale(self) -> None:
        m = self.manifest()
        m["published"] = ur.now() - 15 * DAY
        s = ur.summary(m, {**ur.empty_verdict(), "cards": {"C01": {"v": "❓"}}})
        self.assertEqual((s["need"], s["counts"]["❓"], s["decided"], s["stale"]), (1, 1, False, True))
        s = ur.summary(m, {**ur.empty_verdict(), "cards": {"C01": {"v": "✅"}}})
        self.assertEqual((s["decided"], s["stale"]), (True, False))

    def test_remaining_ignores_verdicts_on_unchanged_cards(self) -> None:
        s = ur.summary(self.manifest(), {**ur.empty_verdict(), "cards": {"C02": {"v": "✅"}}})
        self.assertEqual((s["remaining"], s["decided"]), (1, False))


class ApplyVerdict(Base):
    def test_rev_conflict_and_decided_at(self) -> None:
        self.publish_run("r1", ["CHANGED", "UNCHANGED"])
        status, v = ur.apply_verdict("r1", {"rev": 0, "cards": {"C01": {"v": "✅", "note": " ok "}}})
        self.assertEqual((status, v["rev"], v["cards"]["C01"]["note"]), (200, 1, "ok"))
        self.assertIsNotNone(v["decided_at"])
        status, v = ur.apply_verdict("r1", {"rev": 0, "cards": {"C01": {"v": "❌"}}})
        self.assertEqual((status, v["cards"]["C01"]["v"]), (409, "✅"))
        status, v = ur.apply_verdict("r1", {"rev": 1, "cards": {"C01": {"v": "❓"}}})
        self.assertEqual((status, v["decided_at"]), (200, None))

    def test_rejects_bad_bodies(self) -> None:
        self.publish_run("r1", ["CHANGED"])
        for body in ({"cards": {}}, {"rev": 0, "extra": 1}, {"rev": 0, "cards": {"C09": {"v": "✅"}}},
                     {"rev": 0, "cards": {"C01": {"v": "👍"}}}, {"rev": 0, "cards": {"C01": {"v": "✅", "note": "x" * 1001}}},
                     {"rev": 0, "closed": "false"}, {"rev": True}, {"rev": 0, "cards": {"C01": {"v": "✅", "note": None}}}):
            with self.subTest(body=body):
                self.assertEqual(ur.apply_verdict("r1", body)[0], 400)


class PrunePlan(Base):
    def planned(self) -> dict[str, str]:
        return {str(p.relative_to(self.root)): why for p, why in ur.prune_plan()}

    def base(self, name: str, created: float) -> None:
        ur.write_json(ur.sub("base") / name / "base.json", {"id": name, "project": "demo", "created": created})

    def work(self, run_id: str, created: float, base: str | None = None) -> None:
        ur.write_json(ur.work(run_id) / "capture.json", {"run": run_id, "created": created,
                                                          "base": {"id": base} if base else None})

    def test_retention_rules(self) -> None:
        t = ur.now()
        self.publish_run("r1", ["CHANGED"], published=t - 60 * DAY, base="b-live")          # pending, ancient
        self.publish_run("r2", ["CHANGED"], {"cards": {"C01": {"v": "✅"}}, "decided_at": t - 8 * DAY}, base="b-old")
        self.publish_run("r3", ["CHANGED"], {"closed": True, "decided_at": t - 2 * DAY}, base="b-recent")
        self.work("r1", t - 60 * DAY, "b-live")
        self.work("r2", t - 9 * DAY, "b-old")
        self.work("r3", t - 3 * DAY, "b-recent")
        self.work("r4", t - 4 * DAY)                                                         # draft never published
        self.work("r5", t - 1 * DAY)                                                         # fresh draft
        self.base("b-live", t - 60 * DAY)
        self.base("b-old", t - 9 * DAY)
        self.base("b-recent", t - 3 * DAY)
        self.base("b-idle", t - 15 * DAY)
        self.base("b-new", t - 1 * DAY)
        plan = self.planned()
        self.assertEqual(set(plan), {"runs/r2", "work/r2", "work/r3", "work/r4", "base/b-old", "base/b-idle"})

    def test_run_with_nothing_to_judge_expires_from_publish(self) -> None:
        t = ur.now()
        self.publish_run("r1", ["UNCHANGED"], published=t - 8 * DAY, base="b1")
        self.base("b1", t - 8 * DAY)
        self.assertEqual(set(self.planned()), {"runs/r1", "base/b1"})

    def test_pending_run_keeps_its_base_forever(self) -> None:
        t = ur.now()
        self.publish_run("r1", ["CHANGED"], published=t - 90 * DAY, base="b1")
        self.base("b1", t - 90 * DAY)
        self.assertEqual(self.planned(), {})


@unittest.skipUnless(HAS_MAGICK, "needs ImageMagick (magick)")
class Publish(Base):
    def make_capture(self, identical: bool = True) -> Path:
        folder = ur.work("r1")
        shots = []
        for side, color in (("before", "white"), ("after", "white" if identical else "gray")):
            out = folder / "shots" / side / "home.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            ur.magick("-size", "200x100", f"xc:{color}", str(out))
            shots.append({"name": "home", "side": side, "label": "Home", "file": str(out.relative_to(folder)),
                          "sha256": ur.sha256_file(out), "time": ur.now(), "stable": True, "ax": None})
        capture = {"run": "r1", "project": "demo", "title": "A/A", "created": ur.now(), "round_of": None,
                   "base": {"id": "b1", "hash": "h", "git": {}}, "after": {"hash": "h", "git": {}},
                   "identical_builds": identical, "sides": {}, "shots": shots}
        ur.write_json(folder / "capture.json", capture)
        ur.write_json(folder / "notes.json", ur.skeleton(capture))
        return folder

    def publish(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                unittest.mock.patch.object(ur, "site_checks", return_value=[]):
            ur.cmd_publish(type("Args", (), {"run": "r1"})())

    def test_identical_builds_publish_unchanged(self) -> None:
        self.make_capture(identical=True)
        self.publish()
        manifest = ur.read_json(ur.sub("runs") / "r1" / "manifest.json")
        self.assertEqual([c["status"] for c in manifest["cards"]], ["UNCHANGED"])
        self.assertTrue((ur.sub("runs") / "r1" / "C01-after.webp").exists())
        decided_at = ur.read_json(ur.sub("runs") / "r1" / "verdict.json")["decided_at"]
        self.assertIsNotNone(decided_at)
        self.assertIn(ur.sub("runs") / "r1", [p for p, _ in ur.prune_plan(decided_at + 8 * DAY)])

    def test_unreachable_site_fails_after_publishing(self) -> None:
        self.make_capture(identical=True)
        broken = [(False, "server answers on 127.0.0.1:8788", "")]
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()), \
                unittest.mock.patch.object(ur, "site_checks", return_value=broken), self.assertRaises(SystemExit) as stop:
            ur.cmd_publish(type("Args", (), {"run": "r1"})())
        self.assertEqual((stop.exception.code, out.getvalue()), (1, ""))
        self.assertTrue((ur.sub("runs") / "r1" / "manifest.json").exists())

    def test_changed_card_without_caption_is_rejected(self) -> None:
        self.make_capture(identical=False)
        with self.assertRaisesRegex(ur.Fail, "`what` is required"):
            self.publish()

    def test_tampered_shot_is_rejected(self) -> None:
        folder = self.make_capture()
        ur.magick("-size", "200x100", "xc:black", str(folder / "shots/after/home.png"))
        with self.assertRaisesRegex(ur.Fail, "changed after capture"):
            self.publish()
        self.assertFalse((ur.sub("runs") / "r1").exists())


class CaptureNeedsABase(Base):
    def test_missing_base_fails_unless_after_only_is_asked_for(self) -> None:
        recipe = self.root / "recipe.sh"
        recipe.write_text("true\n")
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
            ur.main(["capture", "--project", "demo", "--udid", "U", "--bundle", "b", "--app", str(self.root),
                     "--recipe", str(recipe), "--title", "t"])
        self.assertEqual(stop.exception.code, 1)
        self.assertIn("--no-base", err.getvalue())
        self.assertFalse((self.root / "counter").exists())

    def test_missing_before_shot_is_new_in_compare_and_screen_in_screens(self) -> None:
        shots = {("after", "home"): {"file": "x"}}
        self.assertEqual(ur.card_status({"run": "r1", "base": {"id": "b"}}, "home", shots), "NEW")
        self.assertEqual(ur.card_status({"run": "r1", "base": None}, "home", shots), "SCREEN")


@unittest.skipUnless(HAS_MAGICK, "needs ImageMagick (magick)")
class Interactive(Base):
    """`start` + `shot --run`: an after-only run shot while the agent drives the simulator."""

    def setUp(self) -> None:
        super().setUp()
        self.installed, self.color = "h1", "white"
        real_run = ur.run

        def offline(cmd: list[str], **kw):  # simulator, git and tailscale are not part of these tests
            if cmd[0] in ("sim-use", "xcrun", "git", "tailscale"):
                return subprocess.CompletedProcess(cmd, 1, "", "")
            return real_run(cmd, **kw)

        patches = [unittest.mock.patch.object(ur, "installed_app", lambda udid, bundle: Path("/fake.app")),
                   unittest.mock.patch.object(ur, "hash_tree", lambda path: self.installed),
                   unittest.mock.patch.object(ur, "screenshot", lambda udid, out: ur.magick(
                       "-size", "200x100", f"xc:{self.color}", str(out))),
                   unittest.mock.patch.object(ur, "run", offline),
                   unittest.mock.patch.object(ur, "site_checks", return_value=[])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def cli(self, *argv: str) -> tuple[int, str]:
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                ur.main(list(argv))
            except SystemExit as stop:
                return stop.code, out.getvalue() + err.getvalue()
        return 0, out.getvalue() + err.getvalue()

    def start(self) -> None:
        code, _ = self.cli("start", "--project", "demo", "--udid", "U", "--bundle", "com.demo", "--title", "Gate 1")
        self.assertEqual(code, 0)

    def shoot(self, name: str) -> tuple[int, str]:
        return self.cli("shot", name, "--run", "r1", "--label", name.title(), "--interval", "0")

    def notes(self) -> dict:
        return ur.read_json(ur.work("r1") / "notes.json")

    def test_shots_grow_the_notes_and_publish_as_screens(self) -> None:
        self.start()
        self.assertEqual(self.notes()["cards"], [])
        self.assertEqual(self.shoot("empty")[0], 0)
        notes = self.notes()
        notes["cards"][0]["what"] = "empty state copy"
        ur.write_json(ur.work("r1") / "notes.json", notes)
        self.color = "gray"
        self.assertEqual(self.shoot("filled")[0], 0)
        cards = self.notes()["cards"]
        self.assertEqual([(c["id"], c["name"], c["what"]) for c in cards], [("C01", "empty", "empty state copy"), ("C02", "filled", "")])
        code, out = self.cli("publish", "r1")
        self.assertEqual(code, 1)
        self.assertIn("`what` is required for a SCREEN card", out)
        notes = self.notes()
        notes["cards"][1]["what"] = "two products"
        ur.write_json(ur.work("r1") / "notes.json", notes)
        self.assertEqual(self.cli("publish", "r1")[0], 0)
        manifest = ur.read_json(ur.sub("runs") / "r1" / "manifest.json")
        self.assertEqual((manifest["mode"], [c["status"] for c in manifest["cards"]]), ("screens", ["SCREEN", "SCREEN"]))
        self.assertEqual(["before" in c for c in manifest["cards"]], [False, False])

    def test_identical_screens_warn(self) -> None:
        self.start()
        self.shoot("one")
        self.assertIn("pixel-identical to one", self.shoot("two")[1])

    def test_rebuilt_app_is_refused(self) -> None:
        self.start()
        self.installed = "h2"
        code, out = self.shoot("empty")
        self.assertEqual(code, 1)
        self.assertIn("not the after build h1", out)
        self.assertIn("uireview start", out)

    def test_broken_notes_stop_the_shot_before_it_is_recorded(self) -> None:
        self.start()
        (ur.work("r1") / "notes.json").write_text('{"cards": [],}')
        code, out = self.shoot("empty")
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out)
        self.assertEqual(ur.load_capture("r1")["shots"], [])

    def test_run_flag_refuses_a_recipe_run(self) -> None:
        ur.write_json(ur.work("r1") / "capture.json", {"run": "r1", "interactive": False, "udid": "U", "shots": []})
        code, out = self.shoot("empty")
        self.assertEqual(code, 1)
        self.assertIn("replays a recipe", out)

    def test_run_ids_accept_the_uppercase_the_site_shows(self) -> None:
        self.publish_run("r7", ["CHANGED"])
        code, out = self.cli("close", "R7")
        self.assertEqual((code, out.strip()), (0, "r7 closed"))
        self.assertTrue(ur.read_json(ur.sub("runs") / "r7" / "verdict.json")["closed"])
        self.assertEqual(self.cli("verdict", "rx")[0], 2)
        code, _ = self.cli("start", "--project", "demo", "--udid", "U", "--bundle", "com.demo", "--title", "T", "--round-of", "R7")
        self.assertEqual(code, 0)
        self.assertEqual(ur.load_capture("r1")["round_of"], "r7")
        self.assertEqual(self.cli("start", "--project", "demo", "--udid", "U", "--bundle", "com.demo", "--title", "T",
                                  "--round-of", "latest")[0], 2)

    def test_shot_needs_a_recipe_or_run(self) -> None:
        code, out = self.cli("shot", "empty")
        self.assertEqual(code, 1)
        self.assertIn("uireview start", out)


FAKE_RECORDER = r'''
import signal, subprocess, sys, time
out, mode = sys.argv[1], sys.argv[2]
def stop(*_):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x200:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", out], check=True)
    sys.exit(0)
signal.signal(signal.SIGINT, signal.SIG_IGN if mode == "hang" else stop)
if mode != "silent":
    print("Recording started", file=sys.stderr, flush=True)
while True:
    time.sleep(0.05)
'''


class Recorder(unittest.TestCase):
    def spawn(self, mode: str) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", FAKE_RECORDER, os.devnull, mode], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True)

    def test_stack_filter_pads_the_shorter_side(self) -> None:
        self.assertEqual(ur.stack_filter((1.0, 2.5)), "[0]tpad=stop_mode=clone:stop_duration=2.000[v0];"
                         "[1]tpad=stop_mode=clone:stop_duration=0.500[v1];[v0][v1]vstack")

    def test_handshake(self) -> None:
        proc = self.spawn("silent")
        self.assertFalse(ur.wait_started(proc, 0.5))
        proc.kill(), proc.wait()

    @unittest.mock.patch.object(ur, "STOP_WAIT", 0.3)
    def test_hung_recorder_is_killed_and_flagged(self) -> None:
        proc = self.spawn("hang")
        self.assertTrue(ur.wait_started(proc, 5))
        self.assertFalse(ur.stop_recorder(proc))
        self.assertIsNotNone(proc.returncode)


@unittest.skipUnless(HAS_MAGICK and shutil.which("ffmpeg"), "needs ImageMagick and ffmpeg")
class Clip(Base):
    def setUp(self) -> None:
        super().setUp()
        folder = ur.work("r1")
        shots = []
        for side in ("before", "after"):
            out = folder / "shots" / side / "menu.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            ur.magick("-size", "200x100", "xc:white", str(out))
            shots.append({"name": "menu", "side": side, "label": None, "file": str(out.relative_to(folder)),
                          "sha256": ur.sha256_file(out), "time": ur.now(), "stable": True, "ax": None})
        ur.write_json(folder / "capture.json", {
            "run": "r1", "project": "demo", "title": "menu", "created": ur.now(), "round_of": None, "rotate": 0, "bundle": "com.demo",
            "base": {"id": "b1", "hash": "h0", "git": {}}, "after": {"hash": "h1", "git": {}}, "identical_builds": False,
            "sides": {}, "shots": shots, "clips": []})
        patches = [unittest.mock.patch.object(ur, "LEAD_IN", 0), unittest.mock.patch.object(ur, "STOP_WAIT", 0.5),
                   unittest.mock.patch.object(ur, "stop_leftover_recorders", lambda udid: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def clip(self, side: str, mode: str, name: str = "menu", command: tuple = ("true",), installed: str | None = None) -> int:
        fake = lambda udid, out: [sys.executable, "-c", FAKE_RECORDER, str(out), mode]  # noqa: E731
        env = {"UIREVIEW_RUN": "r1", "UIREVIEW_SIDE": side, "UIREVIEW_UDID": "FAKE"}
        installed = installed or {"before": "h0", "after": "h1"}[side]
        with unittest.mock.patch.object(ur, "recorder_cmd", fake), unittest.mock.patch.dict(os.environ, env), \
                unittest.mock.patch.object(ur, "installed_app", lambda udid, bundle: Path("/fake.app")), \
                unittest.mock.patch.object(ur, "hash_tree", lambda path: installed), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                ur.main(["clip", name, "--settle", "0", "--", *command])
            except SystemExit as stop:
                return stop.code
        return 0

    def publish(self, what: str = "menu slides in") -> dict:
        notes = ur.skeleton(ur.load_capture("r1"))
        notes["cards"][0]["what"] = what
        ur.write_json(ur.work("r1") / "notes.json", notes)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                unittest.mock.patch.object(ur, "site_checks", return_value=[]):
            ur.cmd_publish(type("Args", (), {"run": "r1"})())
        return ur.read_json(ur.sub("runs") / "r1" / "manifest.json")["cards"][0]

    def test_both_sides_stack_into_one_video_and_identical_stills_become_motion(self) -> None:
        self.assertEqual(self.clip("before", "ok"), 0)
        self.assertEqual(self.clip("after", "ok", command=("false",)), 1)
        clips = ur.load_capture("r1")["clips"]
        self.assertEqual([(c["side"], c["action_exit"], bool(c["file"])) for c in clips], [("before", 0, True), ("after", 1, True)])
        card = self.publish()
        self.assertEqual((card["status"], card["video"]["sides"], card["video_error"]), ("MOTION", ["before", "after"], None))
        size = ur.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                       str(ur.sub("runs") / "r1" / card["video"]["src"])]).stdout.strip()
        self.assertEqual(size, "1280,1600")

    def test_hung_recorder_fails_only_that_video(self) -> None:
        self.clip("before", "ok")
        self.clip("after", "hang")
        after = ur.load_capture("r1")["clips"][1]
        self.assertEqual((after["needs_reboot"], after["file"]), (True, None))
        card = self.publish()
        self.assertEqual(card["video"]["sides"], ["before"])
        self.assertIn("reboot", card["video_error"])

    def test_clip_needs_a_shot_and_untouched_file(self) -> None:
        self.clip("after", "ok", name="orphan")
        with self.assertRaisesRegex(ur.Fail, "has no `uireview shot orphan`"):
            self.publish()

    def test_reinstalled_build_is_refused(self) -> None:
        self.assertEqual(self.clip("before", "ok", installed="h1"), 1)
        self.assertEqual(ur.load_capture("r1")["clips"], [])

    def test_clip_cap_counts_names_across_sides(self) -> None:
        capture = ur.load_capture("r1")
        capture["clips"] = [{"name": n, "side": "before", "file": None, "error": "x"} for n in ("a", "b", "c")]
        ur.write_json(ur.work("r1") / "capture.json", capture)
        self.assertEqual(self.clip("after", "silent", name="d"), 1)
        self.assertEqual(len(ur.load_capture("r1")["clips"]), 3)

    def test_interrupt_with_hung_recorder_still_exits_130(self) -> None:
        code = self.clip("after", "hang", command=("sh", "-c", f"kill -TERM {os.getpid()}; sleep 5"))
        record = ur.load_capture("r1")["clips"][0]
        self.assertEqual((code, record["needs_reboot"]), (130, True))
        self.assertIn("interrupted by SIGTERM", record["error"])

    def test_tampered_clip_is_rejected(self) -> None:
        self.clip("after", "ok")
        clip = ur.work("r1") / ur.load_capture("r1")["clips"][0]["file"]
        clip.write_bytes(clip.read_bytes() + b"x")
        with self.assertRaisesRegex(ur.Fail, "changed after capture"):
            self.publish()


class Server(Base):
    def setUp(self) -> None:
        super().setUp()
        self.server = ur.http.server.ThreadingHTTPServer(("127.0.0.1", 0), ur.Handler)
        ur.Handler.log_message = lambda *a: None
        hosts = unittest.mock.patch.object(ur, "tailnet_hosts", return_value={"air:8787"})
        hosts.start()
        self.addCleanup(hosts.stop)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, path: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, dict(res.headers), res.read()
        except urllib.error.HTTPError as err:
            with err:
                return err.code, dict(err.headers), err.read()

    def test_range_on_run_asset(self) -> None:
        folder = self.publish_run("r1", ["CHANGED"])
        (folder / "C01.mp4").write_bytes(b"0123456789")
        status, headers, body = self.request("/runs/r1/C01.mp4", headers={"Range": "bytes=2-4"})
        self.assertEqual((status, body, headers["Content-Range"]), (206, b"234", "bytes 2-4/10"))
        self.assertEqual(self.request("/runs/r1/C01.mp4", headers={"Range": "bytes=20-"})[0], 416)
        self.assertEqual(self.request("/runs/r1/.hidden")[0], 404)
        self.assertEqual(self.request("/runs/r1/..%2Fx")[0], 404)

    def test_verdict_post_guards(self) -> None:
        self.publish_run("r1", ["CHANGED"])
        body = json.dumps({"rev": 0, "cards": {"C01": {"v": "✅"}}}).encode()
        json_headers = {"Content-Type": "application/json", "X-UIReview": "1"}
        self.assertEqual(self.request("/api/runs/r1/verdict", body, {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("/api/runs/r1/verdict", body, {**json_headers, "Origin": "http://evil"})[0], 403)
        self.assertEqual(self.request("/api/runs/r9/verdict", body, json_headers)[0], 404)
        status, _, raw = self.request("/api/runs/r1/verdict", body, json_headers)
        self.assertEqual((status, json.loads(raw)["rev"]), (200, 1))
        self.assertEqual(self.request("/api/runs/r1/verdict", body, json_headers)[0], 409)
        status, _, raw = self.request("/api/runs")
        self.assertEqual(json.loads(raw)[0]["decided"], True)

    def test_rebound_host_is_refused_even_with_matching_origin(self) -> None:
        self.publish_run("r1", ["CHANGED"])
        body = json.dumps({"rev": 0, "cards": {"C01": {"v": "✅"}}}).encode()
        evil = {"Host": "evil.example:8788", "Origin": "http://evil.example:8788"}
        headers = {"Content-Type": "application/json", "X-UIReview": "1", **evil}
        self.assertEqual(self.request("/api/runs/r1/verdict", body, headers)[0], 403)
        self.assertEqual(self.request("/api/runs", headers=evil)[0], 403)
        self.assertEqual(self.request("/runs/r1/manifest.json", headers=evil)[0], 403)
        tailnet = {"Host": "air:8787", "Origin": "http://air:8787"}
        self.assertEqual(self.request("/api/runs/r1/verdict", body, {**headers, **tailnet})[0], 200)

    def test_negative_content_length_is_refused(self) -> None:
        self.publish_run("r1", ["CHANGED"])
        headers = {"Content-Type": "application/json", "X-UIReview": "1", "Content-Length": "-1"}
        self.assertEqual(self.request("/api/runs/r1/verdict", b"{}", headers)[0], 400)

    def test_shell_refuses_framing(self) -> None:
        status, headers, _ = self.request("/")
        self.assertEqual((status, headers["Content-Security-Policy"]), (200, "frame-ancestors 'none'"))

    def test_shell_serves_its_font_and_nothing_else_from_web(self) -> None:
        status, headers, _ = self.request("/geist.woff2")
        self.assertEqual((status, headers["Content-Type"]), (200, "font/woff2"))
        self.assertEqual(self.request("/geist-OFL.txt")[0], 404)


class Install(Base):
    def test_refuses_to_replace_a_regular_file(self) -> None:
        home = self.root / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/uireview").write_text("custom")
        with unittest.mock.patch.object(ur.Path, "home", return_value=home), \
                self.assertRaisesRegex(ur.Fail, "regular file"):
            ur.cmd_install(None)
        self.assertEqual((home / ".local/bin/uireview").read_text(), "custom")


if __name__ == "__main__":
    unittest.main()
