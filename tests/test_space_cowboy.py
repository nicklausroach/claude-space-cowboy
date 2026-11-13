"""Tests for scripts/space-cowboy. Run from the repo root: python3 -m unittest discover tests"""

import importlib.util
import json
import os
import subprocess
import tempfile
import types
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
        # The window reports remote spaces as "<machine>/<id>"; the remote core wants the bare id.
        hc = load(self.tmp.name, HC_TERMINAL_ID="t4").cowboy_argv(m, ["spawn"], space="devbox/sp9")[-1]
        self.assertIn("CLAUDE_COWBOY_HC_SPACE=sp9 ", hc)
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


PROJECTS = [
    {"id": "p-obs", "metadata": {"name": "Obsidian"},
     "initializer": {"specs": [{"git": {"remoteUri": "https://github.com/V/obsidian.git", "checkoutLocation": "obsidian"}}]},
     "environmentClasses": [{"environmentClassId": "c-lon"}, {"environmentClassId": "c-ohio", "order": 1}]},
    {"id": "p-obs2", "metadata": {"name": "Obsidian (AI DX)"},
     "initializer": {"specs": [{"git": {"remoteUri": "https://github.com/V/obsidian.git", "checkoutLocation": "obsidian"}}]}},
    {"id": "p-dbt", "metadata": {"name": "DBT"},
     "initializer": {"specs": [{"git": {"remoteUri": "https://github.com/V/dbt.git", "checkoutLocation": "dbt"}}]},
     "environmentClasses": [{"environmentClassId": "c-lon"}, {"environmentClassId": "c-ore", "order": 1},
                            {"environmentClassId": "c-ohio", "order": 2}]},
]
CLASSES = [{"id": "c-lon", "runner": "London"}, {"id": "c-ore", "runner": "Oregon"}, {"id": "c-ohio", "runner": "Ohio"}]
ENV_ID = "01a1d283-7be3-77be-8872-a0fbc7ad8824"


class FakeOna:
    """Answers the ona/hc/herdr/ssh calls `env` commands make, recording each."""

    def __init__(self, phases=("ENVIRONMENT_PHASE_STARTING", "ENVIRONMENT_PHASE_RUNNING"), create_err=None):
        self.calls, self.phases, self.create_err, self.machines = [], list(phases), create_err, []

    def __call__(self, argv, **k):
        self.calls.append(argv)
        tool, rest = Path(argv[0]).name, argv[1:]
        if tool == "ona":
            if rest[:2] == ["project", "list"]:
                return done(json.dumps(PROJECTS))
            if rest[:2] == ["environment", "list-classes"]:
                return done(json.dumps(CLASSES))
            if rest[:2] == ["environment", "create"]:
                if self.create_err:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr=f"Error: {self.create_err}")
                return done(f"[WARN ] new version available\n{ENV_ID}\n")
            if rest[:2] == ["environment", "get"]:
                phase = self.phases.pop(0) if len(self.phases) > 1 else self.phases[0]
                return done(json.dumps({"status": {"phase": phase}}))
            return done("")
        if tool == "herdr-app":
            if rest[0] == "ls":
                return done(json.dumps({"spaces": [{"id": "cowboy-x/s1", "machine": "cowboy-x"},
                                                   {"id": "s9", "machine": None}]}))
            return done('{"ok": true}')
        if tool == "hc":
            if rest[:2] == ["machine", "ls"]:
                return done(json.dumps({"machines": self.machines}))
            if rest[:2] == ["machine", "add"]:
                self.machines.append({"name": rest[rest.index("--name") + 1], "target": rest[-1], "via": False,
                                      "state": "connected"})
            return done("{}")
        if tool == "ssh":
            if "sh -s" in argv[-1]:
                return done("ok\tclaude\t2.1\nok\tgh\tsigned in\n")
            return done("")
        if tool == "git":
            return done("me@work.com" if "user.email" in argv else "Me")
        return done("")

    def of(self, *prefix):
        return [c for c in self.calls if c[1:1 + len(prefix)] == list(prefix)]


class OnaEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sc = load(self.tmp.name, HC_TERMINAL_ID="t4")
        self.sc.time.sleep = lambda s: None

    def run_with(self, fake, fn, **args):
        ns = types.SimpleNamespace(**{"json": False, "name": None, "region": None, "class_id": None,
                          "inactivity_timeout": None, "force": False, **args})
        with mock.patch.object(self.sc.subprocess, "run", fake), mock.patch("sys.stdout"):
            fn(ns)

    def test_find_project(self):
        with mock.patch.object(self.sc.subprocess, "run", FakeOna()):
            self.assertEqual(self.sc.find_project("dbt")["id"], "p-dbt")        # by repo name
            self.assertEqual(self.sc.find_project("obsidian")["id"], "p-obs")   # exact name beats repo
            self.assertEqual(self.sc.find_project("p-obs2")["id"], "p-obs2")    # by id
            with self.assertRaisesRegex(self.sc.SpaceError, "no Ona project"):
                self.sc.find_project("nope")
        self.assertEqual(self.sc.project_repos(PROJECTS[2]), ["/workspaces/dbt"])

    def test_pick_class_prefers_region(self):
        with mock.patch.object(self.sc.subprocess, "run", FakeOna()):
            self.assertEqual(self.sc.pick_class(PROJECTS[2], "ohio"), "c-ohio")
            self.assertEqual(self.sc.pick_class(PROJECTS[2], "Oregon"), "c-ore")
            with self.assertRaisesRegex(self.sc.SpaceError, "no environment class in 'Tokyo'"):
                self.sc.pick_class(PROJECTS[2], "Tokyo")

    def test_create(self):
        fake = FakeOna()
        self.run_with(fake, self.sc.cmd_env_create, project="dbt", name="Fix Validation!")
        create = fake.of("environment", "create")[0]
        self.assertEqual(create[3], "p-dbt")
        for flag, val in (("--name", "cowboy-fix-validation"), ("--class-id", "c-ohio"), ("--inactivity-timeout", "4h")):
            self.assertEqual(create[create.index(flag) + 1], val)
        env = json.loads((Path(self.tmp.name) / "envs.json").read_text())["cowboy-fix-validation"]
        self.assertEqual((env["id"], env["target"], env["repos"]),
                         (ENV_ID, f"{ENV_ID}.gitpod.environment", ["/workspaces/dbt"]))
        boot = [c for c in fake.calls if Path(c[0]).name == "ssh" and "sh -s" in c[-1]][0][-1]
        self.assertIn("COWBOY_REPOS=/workspaces/dbt", boot)
        self.assertIn("COWBOY_GIT_EMAIL=me@work.com", boot)
        add = fake.of("machine", "add")[0]
        self.assertNotIn("--temp", add)  # the desktop app hides temporary machines
        self.assertEqual(add[-1], f"{ENV_ID}.gitpod.environment")

    def test_create_reports_missing_github_signin(self):
        fake = FakeOna(create_err="failed_precondition: missing authentication token for github.com")
        with self.assertRaisesRegex(self.sc.SpaceError, "--region"):
            self.run_with(fake, self.sc.cmd_env_create, project="dbt", name="x")
        self.assertFalse((Path(self.tmp.name) / "envs.json").exists())

    def test_failed_bootstrap_keeps_record(self):
        fake = FakeOna()
        real = fake.__call__
        fake_fail = lambda argv, **k: done("fail\tclaude\tinstall failed\n") if "sh -s" in argv[-1] else real(argv, **k)
        with self.assertRaisesRegex(self.sc.SpaceError, "env setup cowboy-x"):
            self.run_with(fake_fail, self.sc.cmd_env_create, project="dbt", name="x")
        self.assertIn("cowboy-x", json.loads((Path(self.tmp.name) / "envs.json").read_text()))
        self.assertEqual(fake.of("machine", "add"), [])

    def test_start_waits_past_stale_stopped_phase(self):
        (Path(self.tmp.name) / "envs.json").write_text(json.dumps(
            {"cowboy-x": {"id": ENV_ID, "target": "t", "repos": [], "project": "DBT", "created_at": 0}}))
        fake = FakeOna(phases=("ENVIRONMENT_PHASE_STOPPED", "ENVIRONMENT_PHASE_STARTING", "ENVIRONMENT_PHASE_RUNNING"))
        self.run_with(fake, self.sc.cmd_env_start, name="cowboy-x")
        self.assertEqual(len(fake.of("machine", "add")), 1)  # re-added to Herdr after the restart
        fake = FakeOna(phases=("ENVIRONMENT_PHASE_STARTING", "ENVIRONMENT_PHASE_STOPPED"))
        with self.assertRaisesRegex(self.sc.SpaceError, "went to ENVIRONMENT_PHASE_STOPPED"):
            self.run_with(fake, self.sc.cmd_env_start, name="cowboy-x")

    def test_delete_only_envs_made_here(self):
        with self.assertRaisesRegex(self.sc.SpaceError, "not an environment made by space-cowboy"):
            self.run_with(FakeOna(), self.sc.cmd_env_delete, name="dbt-primary")

    def test_delete(self):
        (Path(self.tmp.name) / "envs.json").write_text(json.dumps(
            {"cowboy-x": {"id": ENV_ID, "target": "t", "repos": [], "project": "DBT", "created_at": 0}}))
        (Path(self.tmp.name) / "hc-spaces.json").write_text(json.dumps({"cowboy-x:/workspaces/dbt": "s1", "dbt-primary:/w": "s2"}))
        fake = FakeOna(phases=("ENVIRONMENT_PHASE_STOPPED",))
        self.run_with(fake, self.sc.cmd_env_delete, name="cowboy-x")
        self.assertEqual(fake.of("environment", "delete")[0][3:], [ENV_ID, "--dont-wait"])
        self.assertEqual(fake.of("machine", "rm")[0][3], "cowboy-x")
        self.assertEqual(json.loads((Path(self.tmp.name) / "envs.json").read_text()), {})
        self.assertEqual(json.loads((Path(self.tmp.name) / "hc-spaces.json").read_text()), {"dbt-primary:/w": "s2"})
        closed = [json.loads(c[3]) for c in fake.calls if Path(c[0]).name == "herdr-app" and c[1] == "do"]
        self.assertEqual(closed, [{"id": "cowboy-x/s1", "confirmed": True}])  # only that machine's space

    def test_machines_show_env_repos(self):
        (Path(self.tmp.name) / "envs.json").write_text(json.dumps({"cowboy-x": {"id": ENV_ID, "repos": ["/workspaces/dbt"]}}))
        fake = FakeOna()
        fake.machines = [{"name": "cowboy-x", "target": "t", "via": False, "state": "connected"}]
        with mock.patch.object(self.sc.subprocess, "run", fake):
            m = self.sc.machines()["cowboy-x"]
        self.assertEqual((m["repos"], m["ona_env"]), (["/workspaces/dbt"], ENV_ID))


if __name__ == "__main__":
    unittest.main()
