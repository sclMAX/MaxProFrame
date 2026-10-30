"""Weekly bump policy: release selection, pin rewriting and static checks of weekly-bump.yml (T7/S9)."""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from ci import bump_weekly
from ci.tests import test_policy

REPO_ROOT = test_policy.REPO_ROOT
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "weekly-bump.yml"
BASE_URL = "https://github.com/FreeCAD/FreeCAD/releases/download"
SHA_A = "a" * 64
SHA_B = "b" * 64
# Obviously synthetic: it can never collide with a real weekly release.
NEW_TAG = "weekly-2099.01.01"
NEW_SHA = "c" * 64
NEW_URL = f"{BASE_URL}/{NEW_TAG}/FreeCAD_{NEW_TAG}-Linux-x86_64.AppImage"


def asset(name, tag, digest=None):
    entry = {"name": name, "browser_download_url": f"{BASE_URL}/{tag}/{name}"}
    if digest is not None:
        entry["digest"] = digest
    return entry


def weekly_release(tag, digest=None, extra_assets=()):
    name = f"FreeCAD_{tag}-Linux-x86_64.AppImage"
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": True,
        "assets": [
            asset(name + ".zsync", tag),
            asset(f"FreeCAD_{tag}-Windows-x86_64.7z", tag),
            asset(name, tag, digest),
            *extra_assets,
        ],
    }


class SelectLatestWeeklyTests(unittest.TestCase):
    def test_picks_newest_weekly_regardless_of_list_order(self):
        releases = [
            weekly_release("weekly-2026.10.21", f"sha256:{SHA_A}"),
            weekly_release("weekly-2026.11.04", f"sha256:{SHA_B}"),
            weekly_release("weekly-2026.10.28", f"sha256:{SHA_A}"),
        ]
        latest = bump_weekly.select_latest_weekly(releases)
        self.assertEqual(latest["tag"], "weekly-2026.11.04")
        self.assertEqual(latest["asset"], "FreeCAD_weekly-2026.11.04-Linux-x86_64.AppImage")
        self.assertEqual(latest["url"], f"{BASE_URL}/weekly-2026.11.04/FreeCAD_weekly-2026.11.04-Linux-x86_64.AppImage")
        self.assertEqual(latest["sha256"], SHA_B)

    def test_accepts_json_text(self):
        latest = bump_weekly.select_latest_weekly(json.dumps([weekly_release("weekly-2026.10.28")]))
        self.assertEqual(latest["tag"], "weekly-2026.10.28")

    def test_ignores_rc_stable_drafts_and_zsync(self):
        rc = {"tag_name": "26.3rc2", "assets": [asset("FreeCAD_26.3rc2-Linux-x86_64.AppImage", "26.3rc2")]}
        stable = {"tag_name": "1.1.4", "assets": [asset("FreeCAD_1.1.4-Linux-x86_64-py311.AppImage", "1.1.4")]}
        draft = dict(weekly_release("weekly-2027.01.06"), draft=True)
        zsync_only = {
            "tag_name": "weekly-2026.12.02",
            "assets": [asset("FreeCAD_weekly-2026.12.02-Linux-x86_64.AppImage.zsync", "weekly-2026.12.02")],
        }
        windows_only = {
            "tag_name": "weekly-2026.12.09",
            "assets": [asset("FreeCAD_weekly-2026.12.09-Windows-x86_64.7z", "weekly-2026.12.09")],
        }
        releases = [rc, stable, draft, zsync_only, windows_only, weekly_release("weekly-2026.10.28")]
        self.assertEqual(bump_weekly.select_latest_weekly(releases)["tag"], "weekly-2026.10.28")

    def test_ignores_tags_that_only_resemble_weekly(self):
        odd = weekly_release("weekly-2026.10.28-rc1")
        odd["assets"] = [asset("FreeCAD_weekly-2026.10.28-rc1-Linux-x86_64.AppImage", "weekly-2026.10.28-rc1")]
        self.assertIsNone(bump_weekly.select_latest_weekly([odd]))

    def test_missing_digest_is_reported_as_none(self):
        latest = bump_weekly.select_latest_weekly([weekly_release("weekly-2026.10.28")])
        self.assertIsNone(latest["sha256"])

    def test_malformed_digest_is_treated_as_missing(self):
        for digest in ("sha1:" + "a" * 40, "sha256:xyz", "sha256:" + "A" * 63):
            latest = bump_weekly.select_latest_weekly([weekly_release("weekly-2026.10.28", digest)])
            self.assertIsNone(latest["sha256"], digest)

    def test_returns_none_without_weekly_release(self):
        self.assertIsNone(bump_weekly.select_latest_weekly([]))

    def test_rejects_download_url_outside_freecad_releases(self):
        release = weekly_release("weekly-2026.10.28")
        for entry in release["assets"]:
            entry["browser_download_url"] = "https://example.invalid/evil.AppImage"
        self.assertIsNone(bump_weekly.select_latest_weekly([release]))


# Files that hold the pin elsewhere (or point at it) and that `apply` must never write.
UNTOUCHED_FILES = (
    ".github/workflows/ci.yml",
    ".github/workflows/nightly.yml",
    ".github/workflows/weekly-bump.yml",
    "ci/run-tests.FCMacro",
    "ci/run_tests.py",
    "ci/tests/test_policy.py",
)


class RepoCopyMixin:
    def make_repo_copy(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="weekly-bump-test-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel in bump_weekly.PINNED_FILES + UNTOUCHED_FILES:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, target)
        return root

    def snapshot(self, root, files=bump_weekly.PINNED_FILES):
        return {rel: (root / rel).read_bytes() for rel in files}


class ApplyBumpTests(RepoCopyMixin, unittest.TestCase):
    def test_apply_only_writes_targets_json_and_docs(self):
        self.assertEqual(bump_weekly.PINNED_FILES, ("ci/targets.json", "docs/ci.md"))

    def test_read_pinned_returns_current_values(self):
        pinned = bump_weekly.read_pinned(REPO_ROOT)
        self.assertRegex(pinned["tag"], r"^weekly-\d{4}\.\d{2}\.\d{2}$")
        self.assertEqual(pinned["url"], f"{BASE_URL}/{pinned['tag']}/FreeCAD_{pinned['tag']}-Linux-x86_64.AppImage")
        self.assertRegex(pinned["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(pinned["fc"]), 3)
        self.assertEqual(len(pinned["py"]), 2)
        weekly = test_policy.load_targets()["weekly"]
        self.assertEqual(pinned["fc"], tuple(weekly["expected_freecad"]))
        self.assertEqual(pinned["py"], tuple(weekly["expected_python"]))

    def test_apply_changes_only_pinned_values(self):
        root = self.make_repo_copy()
        before = self.snapshot(root)
        old = bump_weekly.read_pinned(root)
        bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        after = self.snapshot(root)

        self.assertEqual(set(before), set(after))
        for rel in before:
            self.assertNotEqual(before[rel], after[rel], f"{rel} must contain pinned values")
        new = bump_weekly.read_pinned(root)
        self.assertEqual(
            (new["tag"], new["url"], new["sha256"], new["fc"], new["py"]),
            (NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14)),
        )

        # Undoing the value substitutions must give back the original bytes: nothing else moved.
        reverse = [
            (NEW_URL, old["url"]),
            (NEW_TAG, old["tag"]),
            (NEW_SHA, old["sha256"]),
            ('"27", "2", "0"', ", ".join(f'"{p}"' for p in old["fc"])),
            ("'27', '2', '0'", ", ".join(f"'{p}'" for p in old["fc"])),
            ("27.2.0", ".".join(old["fc"])),
            ("[3, 14]", f"[{old['py'][0]}, {old['py'][1]}]"),
            ("Python 3.14", f"Python {old['py'][0]}.{old['py'][1]}"),
        ]
        for rel, data in after.items():
            text = data.decode("utf-8")
            for new_value, old_value in reverse:
                text = text.replace(new_value, old_value)
            self.assertEqual(text.encode("utf-8"), before[rel], f"{rel} changed outside the pinned values")

    def test_apply_never_touches_workflows_macro_runner_or_policy_tests(self):
        root = self.make_repo_copy()
        before = self.snapshot(root, UNTOUCHED_FILES)
        bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        self.assertEqual(self.snapshot(root, UNTOUCHED_FILES), before)

    def test_apply_works_when_github_directory_is_absent(self):
        root = self.make_repo_copy()
        shutil.rmtree(root / ".github")
        bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        self.assertFalse((root / ".github").exists())

    def test_apply_keeps_stable_target_and_weekly_policy_fields_untouched(self):
        root = self.make_repo_copy()
        before = json.loads((root / "ci/targets.json").read_text(encoding="utf-8"))
        bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        after = json.loads((root / "ci/targets.json").read_text(encoding="utf-8"))
        self.assertEqual(after["stable"], before["stable"])
        self.assertEqual((after["weekly"]["timeout"], after["weekly"]["blocking"]), (480, False))
        self.assertEqual(after["weekly"]["label"], f"FreeCAD {NEW_TAG}")
        self.assertEqual(after["weekly"]["expected_freecad"], ["27", "2", "0"])
        self.assertEqual(after["weekly"]["expected_python"], [3, 14])

    def test_apply_is_idempotent(self):
        root = self.make_repo_copy()
        args = (root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        bump_weekly.apply_bump(*args)
        first = self.snapshot(root)
        bump_weekly.apply_bump(*args)
        self.assertEqual(self.snapshot(root), first)

    def test_apply_with_current_values_is_a_noop(self):
        root = self.make_repo_copy()
        before = self.snapshot(root)
        pinned = bump_weekly.read_pinned(root)
        bump_weekly.apply_bump(root, pinned["tag"], pinned["url"], pinned["sha256"], pinned["fc"], pinned["py"])
        self.assertEqual(self.snapshot(root), before)

    def test_missing_docs_anchor_fails_loudly_and_writes_nothing(self):
        root = self.make_repo_copy()
        docs = root / "docs" / "ci.md"
        docs.write_text(docs.read_text(encoding="utf-8").replace("Packaging labels (e.g. `", "Packaging names (e.g. `"))
        before = self.snapshot(root)
        with self.assertRaises(bump_weekly.BumpError) as caught:
            bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        self.assertIn("docs/ci.md", str(caught.exception))
        self.assertEqual(self.snapshot(root), before)

    def test_missing_targets_key_fails_loudly_and_writes_nothing(self):
        root = self.make_repo_copy()
        targets = root / "ci" / "targets.json"
        text = targets.read_text(encoding="utf-8")
        weekly = text.index('"weekly"')
        targets.write_text(text[:weekly] + text[weekly:].replace('"expected_python"', '"expected_py"'))
        before = self.snapshot(root)
        with self.assertRaises(bump_weekly.BumpError) as caught:
            bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))
        self.assertIn("targets.json", str(caught.exception))
        self.assertEqual(self.snapshot(root), before)

    def test_missing_weekly_entry_fails_loudly(self):
        root = self.make_repo_copy()
        targets = root / "ci" / "targets.json"
        targets.write_text(json.dumps({"stable": test_policy.load_targets()["stable"]}), encoding="utf-8")
        with self.assertRaises(bump_weekly.BumpError):
            bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))

    def test_missing_pinned_file_fails_loudly(self):
        root = self.make_repo_copy()
        (root / "ci" / "targets.json").unlink()
        with self.assertRaises(bump_weekly.BumpError):
            bump_weekly.apply_bump(root, NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14))

    def test_rejects_malformed_values(self):
        root = self.make_repo_copy()
        before = self.snapshot(root)
        bad = [
            ("weekly-2026.11", NEW_URL, NEW_SHA, ("27", "2", "0"), (3, 14)),
            (NEW_TAG, "https://example.invalid/x.AppImage", NEW_SHA, ("27", "2", "0"), (3, 14)),
            (NEW_TAG, NEW_URL, "xyz", ("27", "2", "0"), (3, 14)),
            (NEW_TAG, NEW_URL, NEW_SHA, ("27", "2"), (3, 14)),
            (NEW_TAG, NEW_URL, NEW_SHA, ("27", "2", "0"), (3,)),
        ]
        for args in bad:
            with self.assertRaises(bump_weekly.BumpError, msg=str(args)):
                bump_weekly.apply_bump(root, *args)
        self.assertEqual(self.snapshot(root), before)


class DetectTests(unittest.TestCase):
    def pinned_release(self):
        return weekly_release(bump_weekly.read_pinned(REPO_ROOT)["tag"], f"sha256:{SHA_A}")

    def test_unchanged_when_latest_is_the_pinned_tag(self):
        result = bump_weekly.detect(REPO_ROOT, [self.pinned_release(), weekly_release("weekly-2026.10.14")])
        self.assertFalse(result["changed"])
        self.assertEqual(result["current"]["tag"], result["latest"]["tag"])

    def test_changed_when_a_newer_weekly_exists(self):
        result = bump_weekly.detect(REPO_ROOT, [self.pinned_release(), weekly_release("weekly-2099.01.06", None)])
        self.assertTrue(result["changed"])
        self.assertEqual(result["latest"]["tag"], "weekly-2099.01.06")
        self.assertIsNone(result["latest"]["sha256"])

    def test_never_proposes_a_downgrade(self):
        result = bump_weekly.detect(REPO_ROOT, [weekly_release("weekly-2020.01.01")])
        self.assertFalse(result["changed"])

    def test_no_weekly_release_is_unchanged(self):
        result = bump_weekly.detect(REPO_ROOT, [])
        self.assertFalse(result["changed"])
        self.assertIsNone(result["latest"])

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "ci" / "bump_weekly.py"), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_detect_prints_json_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            releases = pathlib.Path(tmp) / "releases.json"
            releases.write_text(json.dumps([self.pinned_release()]), encoding="utf-8")
            done = self.run_cli("detect", "--releases-file", str(releases))
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertIs(payload["changed"], False)
        self.assertEqual(payload["current"]["tag"], bump_weekly.read_pinned(REPO_ROOT)["tag"])

    def test_cli_detect_reports_errors_in_json_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            releases = pathlib.Path(tmp) / "releases.json"
            releases.write_text("not json", encoding="utf-8")
            done = self.run_cli("detect", "--releases-file", str(releases))
        self.assertEqual(done.returncode, 0)
        payload = json.loads(done.stdout)
        self.assertIs(payload["changed"], False)
        self.assertTrue(payload["error"])

    def test_cli_apply_rejects_bad_arguments_without_touching_files(self):
        before = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_bytes()
        done = self.run_cli("apply", "weekly-bad", NEW_URL, NEW_SHA, "27.2.0", "3.14")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_bytes(), before)


def job_blocks(text):
    """Split the `jobs:` section into {job_id: block text} using the two-space job indentation."""
    jobs_text = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", jobs_text)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class WeeklyBumpWorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.jobs = job_blocks(cls.text)

    def test_triggers_are_schedule_and_manual_dispatch_only(self):
        header = self.text.split("\njobs:\n", 1)[0]
        on_block = header.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(on_block, r"(?m)^  schedule:\n(?:    #[^\n]*\n)*    - cron: '[^']+'")
        self.assertRegex(on_block, r"(?m)^  workflow_dispatch:")
        self.assertNotRegex(on_block, r"(?m)^  (push|pull_request|pull_request_target):")
        cron = re.search(r"cron: '([^']+)'", on_block).group(1)
        self.assertEqual(len(cron.split()), 5)
        self.assertEqual(cron.split()[4], "3", "weekly run on Wednesday, after the weekly release")

    def test_top_level_permissions_are_read_only(self):
        header = self.text.split("\njobs:\n", 1)[0]
        self.assertRegex(header, r"(?m)^permissions:\n  contents: read\n(?!  )")

    def test_has_detect_and_open_pr_jobs(self):
        self.assertEqual(set(self.jobs), {"detect", "open-pr"})

    def test_only_open_pr_has_write_permissions(self):
        self.assertNotRegex(self.jobs["detect"], r":\s*write")
        self.assertRegex(self.jobs["detect"], r"(?m)^    permissions:\n      contents: read\n")
        open_pr = self.jobs["open-pr"]
        self.assertRegex(open_pr, r"(?m)^      contents: write$")
        self.assertRegex(open_pr, r"(?m)^      pull-requests: write$")
        writes = re.findall(r"(?m)^\s+([a-z-]+): write$", self.text)
        self.assertEqual(sorted(writes), ["contents", "pull-requests"])
        self.assertNotIn("write-all", self.text)
        self.assertNotIn("secrets.", self.text.replace("secrets.GITHUB_TOKEN", ""))

    def test_open_pr_needs_detect_and_runs_only_when_changed(self):
        open_pr = self.jobs["open-pr"]
        self.assertRegex(open_pr, r"(?m)^    needs: detect$")
        self.assertIn("needs.detect.outputs.changed == 'true'", open_pr)

    def test_detect_exposes_required_outputs(self):
        detect = self.jobs["detect"]
        for name in ("changed", "tag", "url", "sha256", "fc_version", "py_version"):
            self.assertRegex(detect, rf"(?m)^      {name}: \$\{{\{{ steps\.\w+\.outputs\.\w+ \}}\}}$", name)

    def test_detect_verifies_checksum_and_runs_freecadcmd_isolated(self):
        detect = self.jobs["detect"]
        self.assertIn("sha256sum", detect)
        self.assertIn("squashfs-root/usr/bin/freecadcmd", detect)
        self.assertIn("-u PYTHONHOME", detect)
        self.assertIn("-u PYTHONPATH", detect)
        self.assertRegex(detect, r"HOME=")
        self.assertIn("FreeCAD.Version()[:3]", detect)
        self.assertIn("sys.version_info[:2]", detect)

    def test_open_pr_never_executes_downloaded_binaries(self):
        open_pr = self.jobs["open-pr"]
        for forbidden in ("AppImage", "freecadcmd", "AppRun", "squashfs-root", "curl ", "wget ", "--appimage-extract"):
            self.assertNotIn(forbidden, open_pr, forbidden)

    def test_open_pr_runs_host_tests_before_publishing(self):
        open_pr = self.jobs["open-pr"]
        tests = open_pr.index("python3 -m unittest discover -s ci/tests -p 'test_*.py'")
        self.assertLess(open_pr.index("ci/bump_weekly.py apply"), tests)
        self.assertLess(tests, open_pr.index("git push origin"))
        self.assertLess(tests, open_pr.index("gh pr create"))

    def test_open_pr_commits_only_the_bump_files_and_guards_against_workflow_changes(self):
        open_pr = self.jobs["open-pr"]
        self.assertIn("git add ci/targets.json docs/ci.md", open_pr)
        self.assertNotIn("git add .github", open_pr)
        self.assertNotIn("git add -A", open_pr)
        guard = open_pr.split("- name: Guard against workflow changes", 1)[1].split("- name:", 1)[0]
        self.assertIn("git diff --name-only", guard)
        self.assertIn("^\\.github/", guard)
        self.assertIn("exit 1", guard)
        self.assertLess(open_pr.index("ci/bump_weekly.py apply"), open_pr.index("- name: Guard against workflow"))
        self.assertLess(open_pr.index("- name: Guard against workflow"), open_pr.index("- name: Run host CI"))
        self.assertLess(open_pr.index("- name: Guard against workflow"), open_pr.index("git push origin"))

    def test_open_pr_handles_an_orphan_branch_by_opening_the_pr_from_it(self):
        open_pr = self.jobs["open-pr"]
        check = open_pr.split("- name: Check for an existing bump", 1)[1].split("- name:", 1)[0]
        self.assertIn("gh pr list", check)
        self.assertIn("--state all", check, "closed or merged PRs must also stop a new bump")
        self.assertIn("git ls-remote --exit-code --heads origin", check)
        for mode in ("skip", "reuse", "create"):
            self.assertIn(f"mode={mode}", check)
        for name in ("Apply the bump", "Run host CI policy tests", "Commit and push the branch"):
            step = open_pr.split(f"- name: {name}", 1)[1].split("- name:", 1)[0]
            self.assertIn("steps.existing.outputs.mode == 'create'", step, name)
        pr_step = open_pr.split("- name: Open the pull request", 1)[1]
        self.assertIn("steps.existing.outputs.mode != 'skip'", pr_step.split("run: |", 1)[0])
        self.assertNotIn("git push", pr_step)
        guard = open_pr.split("- name: Guard against workflow changes", 1)[1].split("- name:", 1)[0]
        self.assertIn("origin/main...FETCH_HEAD", guard, "a reused branch is checked against main too")

    def test_open_pr_branch_commit_and_pr_conventions(self):
        open_pr = self.jobs["open-pr"]
        self.assertIn("ci/weekly-bump-", open_pr)
        self.assertIn('git commit -m "ci: bump pinned weekly to $TAG"', open_pr)
        self.assertIn("--label type:chore", open_pr)
        self.assertIn("gh pr list", open_pr)
        for text in ("SHA-256", "trigger", "reopen"):
            self.assertIn(text, open_pr)

    def test_actions_are_pinned_by_full_sha(self):
        uses = re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(?: # (\S+))?$", self.text)
        self.assertTrue(uses)
        pins = {
            "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
            "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
        }
        for ref, comment in uses:
            name, sha = ref.split("@")
            self.assertIn(name, pins)
            self.assertEqual((sha, comment), pins[name])

    def test_workflow_inputs_reach_shell_only_through_env(self):
        for match in re.finditer(r"(?ms)^\s+run: \|\n(.*?)(?=^\s+- name:|^  \S|\Z)", self.text):
            self.assertNotIn("${{", match.group(1), "expressions inside run scripts must go through env")

    def test_checkouts_do_not_persist_credentials_in_read_only_job(self):
        detect = self.jobs["detect"]
        self.assertIn("persist-credentials: false", detect)

    def test_workflow_hard_codes_no_pinned_hash(self):
        self.assertNotRegex(self.text, r"\b[0-9a-f]{64}\b")


if __name__ == "__main__":
    unittest.main()
