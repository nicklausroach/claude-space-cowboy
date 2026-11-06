"""Tests for scripts/space-cowboy. Run from the repo root: python3 -m unittest discover tests"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "space-cowboy"
CLEAN = ("HERDR_ENV", "HC_TERMINAL_ID", "CLAUDE_COWBOY_BACKEND")


def load(home, **env):
    base = {k: v for k, v in os.environ.items() if k not in CLEAN}
    with mock.patch.dict(os.environ, {**base, "CLAUDE_SPACE_COWBOY_HOME": str(home), **env}, clear=True):
        loader = SourceFileLoader("space_cowboy", str(SCRIPT))
        spec = importlib.util.spec_from_loader("space_cowboy", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    return mod


def done(stdout="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


class SpaceCowboyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_backend_detection(self):
        self.assertEqual(load(self.tmp.name).BACKEND, "herdr")
        self.assertEqual(load(self.tmp.name, HC_TERMINAL_ID="t4").BACKEND, "hc")
        self.assertEqual(load(self.tmp.name, HC_TERMINAL_ID="t4", HERDR_ENV="1").BACKEND, "herdr")

    def test_hc_machines(self):
        sc = load(self.tmp.name, HC_TERMINAL_ID="t4")
        out = {"machines": [{"name": "devbox", "target": "dev.example", "via": False},
                            {"name": "fly", "target": "x", "via": "fly ssh console"}]}
        with mock.patch.object(sc.subprocess, "run", lambda *a, **k: done(json.dumps(out))):
            ms = sc.machines()
        self.assertEqual(list(ms), ["local", "devbox"])  # `--via` machines have no SSH target to use
        self.assertEqual(ms["devbox"]["target"], "dev.example")

    def test_herdr_machines_unchanged(self):
        sc = load(self.tmp.name)
        out = [{"label": "devbox", "target": "dev", "session": "s1", "enabled": True},
               {"label": "off", "target": "o", "enabled": False}]
        with mock.patch.object(sc.subprocess, "run", lambda *a, **k: done(json.dumps(out))):
            ms = sc.machines()
        self.assertEqual(list(ms), ["local", "devbox"])
        self.assertEqual(ms["devbox"]["session"], "s1")

    def test_remote_env(self):
        m = {"label": "devbox", "target": "dev", "session": "s1"}
        hc = load(self.tmp.name, HC_TERMINAL_ID="t4").cowboy_argv(m, ["spawn", "-t", "x"], space="sp9")[-1]
        self.assertIn("CLAUDE_COWBOY_BACKEND=hc", hc)
        self.assertIn("CLAUDE_COWBOY_HC_SPACE=sp9", hc)
        self.assertNotIn("HERDR_SESSION", hc)
        herdr = load(self.tmp.name).cowboy_argv(m, ["status"])[-1]
        self.assertIn("CLAUDE_COWBOY_HERDR_SESSION=s1", herdr)
        self.assertNotIn("BACKEND", herdr)

    def test_remote_space_created_once(self):
        sc = load(self.tmp.name, HC_TERMINAL_ID="t4")
        calls, spaces = [], []

        def fake(argv, **k):
            calls.append(argv)
            if argv[1] == "ls":
                return done(json.dumps({"spaces": [{"id": s} for s in spaces]}))
            spaces.append("sp7")
            return done(json.dumps({"space": "sp7", "tab": "tb1", "terminal": "t5"}))

        m = {"label": "devbox"}
        with mock.patch.object(sc.subprocess, "run", fake):
            self.assertEqual(sc.remote_space(m, "/workspaces/api"), "sp7")
            self.assertEqual(sc.remote_space(m, "/workspaces/api"), "sp7")
        made = [json.loads(c[3]) for c in calls if c[1] == "do"]
        self.assertEqual(made, [{"name": "🐄 api @ devbox", "machine": "devbox", "tab": "shell",
                                 "folder": "/workspaces/api"}])

    def test_name_tabs(self):
        sc = load(self.tmp.name, HC_TERMINAL_ID="t4")
        layout = {"spaces": [{"id": "sp7", "tabs": [
            {"id": "tb1", "name": "shell", "terminals": [{"name": None}]},
            {"id": "tb2", "name": "2", "terminals": [{"name": "cow-abc"}]},
            {"id": "tb3", "name": "my name", "terminals": [{"name": "cow-def"}]}]}]}
        calls = []

        def fake(argv, **k):
            calls.append(argv)
            return done(json.dumps(layout) if argv[1] == "ls" else '{"ok": true}')

        agents = [{"id": "abc", "task_name": "fix", "backend": "hc"},
                  {"id": "def", "task_name": "kept", "backend": "hc"}]
        with mock.patch.object(sc.subprocess, "run", fake):
            sc.name_tabs(agents)
        renames = [json.loads(c[3]) for c in calls if c[1] == "do"]
        self.assertEqual(renames, [{"id": "tb2", "name": "🐄 fix (abc)"}])  # a tab the user named stays


if __name__ == "__main__":
    unittest.main()
