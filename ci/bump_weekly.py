#!/usr/bin/env python3
"""Detect a newer FreeCAD weekly release and rewrite the pinned weekly target (stdlib only).

Subcommands:
  detect  print JSON with the latest published weekly versus the pinned one (always exits 0)
  apply   rewrite exactly the pinned values: TAG URL SHA256 FC_VERSION PY_VERSION
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request

RELEASES_API = "https://api.github.com/repos/FreeCAD/FreeCAD/releases?per_page=100"
DOWNLOAD_PREFIX = "https://github.com/FreeCAD/FreeCAD/releases/download/"

TAG_RE = re.compile(r"^weekly-(\d{4})\.(\d{2})\.(\d{2})$")
ASSET_RE = re.compile(r"^FreeCAD_weekly-[0-9.]+-Linux-x86_64\.AppImage$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_PART_RE = re.compile(r"^\d+$")

CI_WORKFLOW = ".github/workflows/ci.yml"
MACRO = "ci/run-tests.FCMacro"
RUNNER = "ci/run_tests.py"
DOCS = "docs/ci.md"
POLICY_TEST = "ci/tests/test_policy.py"

# Every file holding a weekly pin; the text blocks below are the only parts rewritten in each.
# Tokens: @TAG@ @URL@ @SHA@, @FC@ (27.1.0), @FCQ@ ("27", "1", "0"), @FCS@ ('27', '1', '0'), @PY@ (3.13), @PYT@ (3, 13).
ANCHORS = {
    CI_WORKFLOW: [
        "- target: weekly\n"
        "            label: FreeCAD @TAG@\n"
        "            url: @URL@\n"
        "            sha256: @SHA@\n",
    ],
    MACRO: [
        'elif target == "weekly":\n'
        "        expected_fc = (@FCQ@)\n"
        "        expected_py = (@PYT@)\n"
        '        target_label = "Pinned weekly FreeCAD @TAG@ (Version @FC@, Python @PY@)"\n',
    ],
    RUNNER: [
        "'weekly' (pinned FreeCAD @TAG@ / Python @PY@, informative in CI)",
    ],
    DOCS: [
        "inside the pinned FreeCAD @TAG@ Linux AppImage (--target weekly)",
        "**weekly FreeCAD @TAG@** (reports Version @FC@, Python @PY@)",
        "(such as 1.1.4 and @TAG@)",
        "strictly verifies FreeCAD @FC@ (`FreeCAD.Version()[:3] == (@FCS@)`) and embedded Python @PY@.",
        "Packaging labels (e.g. `@TAG@`)",
        "internal Version tuple (`@FC@`)",
        "Python 3.11 / Python @PY@",
        "- Weekly: FreeCAD @TAG@ (`@SHA@`).",
    ],
    POLICY_TEST: [
        "@TAG@",
        "@SHA@",
        "fc_version=(@FCQ@)",
        "py_version=(@PYT@, 0)",
        "FreeCAD @FC@",
        'assertIn("@FC@", content)',
        "Python @PY@",
        "non-@PY@",
    ],
}
PINNED_FILES = tuple(ANCHORS)


class BumpError(Exception):
    """Raised when inputs are malformed or an expected anchor is missing."""


def _tag_key(tag):
    return tuple(int(part) for part in TAG_RE.match(tag).groups())


def _valid_digest(digest):
    if isinstance(digest, str) and digest.startswith("sha256:") and SHA256_RE.match(digest[7:]):
        return digest[7:]
    return None


def select_latest_weekly(releases_json):
    """Return the newest weekly release with a Linux x86_64 AppImage asset, or None.

    The result has tag, asset, url and sha256 (from the API digest, None when absent or malformed).
    """
    releases = json.loads(releases_json) if isinstance(releases_json, (str, bytes)) else releases_json
    best = None
    for release in releases:
        tag = release.get("tag_name", "")
        if release.get("draft") or not TAG_RE.match(tag):
            continue
        for entry in release.get("assets", []):
            name = entry.get("name", "")
            url = entry.get("browser_download_url", "")
            if not ASSET_RE.match(name) or not url.startswith(DOWNLOAD_PREFIX) or not url.endswith("/" + name):
                continue
            if best is None or _tag_key(tag) > _tag_key(best["tag"]):
                best = {"tag": tag, "asset": name, "url": url, "sha256": _valid_digest(entry.get("digest"))}
            break
    return best


def _read(repo_root, rel):
    path = pathlib.Path(repo_root) / rel
    try:
        return path.read_bytes().decode("utf-8")
    except OSError as exc:
        raise BumpError(f"cannot read {rel}: {exc}") from exc


def read_pinned(repo_root):
    """Read the currently pinned weekly values from ci.yml and the macro."""
    workflow = _read(repo_root, CI_WORKFLOW)
    block = re.search(
        r"- target: weekly\n\s+label: FreeCAD (?P<tag>weekly-\d{4}\.\d{2}\.\d{2})\n"
        r"\s+url: (?P<url>\S+)\n\s+sha256: (?P<sha>[0-9a-f]{64})\n",
        workflow,
    )
    if not block:
        raise BumpError(f"{CI_WORKFLOW}: weekly matrix entry (label, url, sha256) not found")
    macro = _read(repo_root, MACRO)
    versions = re.search(
        r'elif target == "weekly":\n\s+expected_fc = \("(\d+)", "(\d+)", "(\d+)"\)\n\s+expected_py = \((\d+), (\d+)\)\n',
        macro,
    )
    if not versions:
        raise BumpError(f"{MACRO}: weekly expected_fc/expected_py branch not found")
    groups = versions.groups()
    return {
        "tag": block["tag"],
        "url": block["url"],
        "sha256": block["sha"],
        "fc": tuple(groups[:3]),
        "py": (int(groups[3]), int(groups[4])),
    }


def _tokens(tag, url, sha256, fc, py):
    return {
        "@TAG@": tag,
        "@URL@": url,
        "@SHA@": sha256,
        "@FC@": ".".join(fc),
        "@FCQ@": ", ".join(f'"{part}"' for part in fc),
        "@FCS@": ", ".join(f"'{part}'" for part in fc),
        "@PY@": f"{py[0]}.{py[1]}",
        "@PYT@": f"{py[0]}, {py[1]}",
    }


def _render(template, tokens):
    for token, value in tokens.items():
        template = template.replace(token, value)
    return template


def _validate(tag, url, sha256, fc, py):
    if not TAG_RE.match(tag):
        raise BumpError(f"tag must look like weekly-YYYY.MM.DD, got {tag!r}")
    if not (url.startswith(DOWNLOAD_PREFIX + tag + "/") and url.endswith("-Linux-x86_64.AppImage")):
        raise BumpError(f"url must be a {tag} Linux x86_64 AppImage under {DOWNLOAD_PREFIX}, got {url!r}")
    if not SHA256_RE.match(sha256):
        raise BumpError("sha256 must be 64 lowercase hex characters")
    if len(fc) != 3 or not all(VERSION_PART_RE.match(str(part)) for part in fc):
        raise BumpError(f"FreeCAD version must be three numeric parts, got {fc!r}")
    if len(py) != 2 or not all(isinstance(part, int) and part >= 0 for part in py):
        raise BumpError(f"Python version must be two numeric parts, got {py!r}")


def apply_bump(repo_root, tag, url, sha256, fc_version_tuple, py_tuple):
    """Rewrite the pinned weekly values in place; nothing is written unless every anchor matches."""
    fc = tuple(str(part) for part in fc_version_tuple)
    py = tuple(py_tuple)
    _validate(tag, url, sha256, fc, py)
    old = read_pinned(repo_root)
    old_tokens = _tokens(old["tag"], old["url"], old["sha256"], old["fc"], old["py"])
    new_tokens = _tokens(tag, url, sha256, fc, py)

    updates = {}
    for rel, templates in ANCHORS.items():
        text = _read(repo_root, rel)
        for template in templates:
            old_text = _render(template, old_tokens)
            if old_text not in text:
                raise BumpError(f"{rel}: expected anchor not found: {old_text!r}")
            text = text.replace(old_text, _render(template, new_tokens))
        updates[rel] = text
    for rel, text in updates.items():
        (pathlib.Path(repo_root) / rel).write_bytes(text.encode("utf-8"))
    return sorted(updates)


def detect(repo_root, releases_json):
    """Compare the latest published weekly with the pin; `changed` only for a strictly newer tag."""
    pinned = read_pinned(repo_root)
    latest = select_latest_weekly(releases_json)
    changed = latest is not None and _tag_key(latest["tag"]) > _tag_key(pinned["tag"])
    current = {"tag": pinned["tag"], "url": pinned["url"], "sha256": pinned["sha256"]}
    return {"changed": changed, "current": current, "latest": latest}


def fetch_releases():
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "maxproframe-weekly-bump",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _parse_version(text, parts, label):
    pieces = text.split(".")
    if len(pieces) != parts or not all(VERSION_PART_RE.match(piece) for piece in pieces):
        raise BumpError(f"{label} must have {parts} numeric parts separated by dots, got {text!r}")
    return tuple(pieces)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-root", default=str(pathlib.Path(__file__).resolve().parent.parent), help="repository root"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    detect_parser = sub.add_parser("detect", help="print the latest weekly versus the pinned one as JSON")
    detect_parser.add_argument("--releases-file", help="read the releases JSON from a file instead of the API")
    apply_parser = sub.add_parser("apply", help="rewrite the pinned weekly values")
    apply_parser.add_argument("tag", help="weekly-YYYY.MM.DD")
    apply_parser.add_argument("url", help="AppImage download URL")
    apply_parser.add_argument("sha256", help="AppImage SHA-256")
    apply_parser.add_argument("fc_version", help="FreeCAD.Version()[:3] joined by dots, e.g. 27.1.0")
    apply_parser.add_argument("py_version", help="Python major.minor, e.g. 3.13")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "detect":
        try:
            if args.releases_file:
                releases = pathlib.Path(args.releases_file).read_text(encoding="utf-8")
            else:
                releases = fetch_releases()
            result = detect(args.repo_root, releases)
        except Exception as exc:  # detect always exits 0; the workflow fails on the `error` field
            result = {"changed": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"bump_weekly: detect failed: {result['error']}", file=sys.stderr)
        print(json.dumps(result, indent=2))
        return 0
    try:
        fc = _parse_version(args.fc_version, 3, "fc_version")
        py = tuple(int(part) for part in _parse_version(args.py_version, 2, "py_version"))
        files = apply_bump(args.repo_root, args.tag, args.url, args.sha256, fc, py)
    except BumpError as exc:
        print(f"bump_weekly: {exc}", file=sys.stderr)
        return 2
    print("bump_weekly: updated " + ", ".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
