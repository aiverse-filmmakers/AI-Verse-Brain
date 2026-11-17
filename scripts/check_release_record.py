"""Release record guard.

Fails when release/component-release.json and the code it points at drift apart.
The record names an accepted commit ("revision") and a version. This script reads
the version files AT THAT COMMIT with git show and compares them to the record.

Default (warn only): problems print as GitHub warnings and the exit code is 0.
Strict (--strict or RELEASE_GUARD_STRICT=1): exit code 1 when a problem is found.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RECORD_PATH = "release/component-release.json"
STALE_AFTER_COMMITS = 50
SHA = re.compile(r"^[0-9a-f]{40}$")
SCHEMA = "ai-verse.component-release/v1"


def git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8"
    )
    return proc.returncode, proc.stdout, proc.stderr


def to_pep440(display):
    """0.1.0-beta.3.dev3 -> 0.1.0b3.dev3 (the form used for __version__)."""
    m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?(?:\.dev(\d+))?", display)
    if not m:
        return None
    base, pre, num, dev = m.groups()
    short = {"alpha": "a", "beta": "b", "rc": "rc"}
    out = base + (short[pre] + num if pre else "")
    return out + (".dev" + dev if dev is not None else "")


def load_record(repo, problems):
    path = Path(repo) / RECORD_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"The release record {RECORD_PATH} cannot be read as JSON ({exc}).")
        return None
    if not isinstance(data, dict):
        problems.append("The release record is not a JSON object.")
        return None
    if data.get("schema_version") != SCHEMA:
        problems.append(f"The release record schema_version is not {SCHEMA}.")
    for key in ("version", "revision", "release_status"):
        if not isinstance(data.get(key), str) or not data.get(key):
            problems.append(f"The release record is missing a text field named {key}.")
    if isinstance(data.get("revision"), str) and not SHA.match(data["revision"]):
        problems.append("The release record revision is not a full 40 character commit id.")
    return data


def check_evidence(data, problems):
    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        problems.append("The release record has no evidence section.")
        return
    seen = {}
    for group in ("ci", "acceptance"):
        entries = evidence.get(group)
        if not isinstance(entries, list):
            problems.append(f"The release record evidence.{group} is not a list.")
            continue
        for entry in entries:
            run_id = entry.get("run_id") if isinstance(entry, dict) else None
            if run_id is None:
                problems.append(f"An evidence.{group} entry has no run_id.")
                continue
            run_id = str(run_id)
            if run_id in seen:
                problems.append(
                    f"CI run {run_id} is listed twice as separate evidence "
                    f"(evidence.{seen[run_id]} and evidence.{group}). "
                    "One run is one proof, not two."
                )
            else:
                seen[run_id] = group


def check_versions_at_commit(repo, revision, version, problems):
    pep = to_pep440(version)
    if pep is None:
        problems.append(f"The record version {version} is not in the form 0.1.0-beta.3.dev3.")
        return

    def show(path):
        code, out, _ = git(repo, "show", f"{revision}:{path}")
        if code != 0:
            problems.append(f"{path} does not exist at the accepted commit {revision[:12]}.")
            return None
        return out

    text = show("engine/aiverse_brain/_version.py")
    if text is not None:
        for name, want in (("DISPLAY_VERSION", version), ("__version__", pep)):
            m = re.search(rf'^{name}\s*=\s*"([^"]*)"', text, re.M)
            have = m.group(1) if m else None
            if have != want:
                problems.append(
                    f"engine/aiverse_brain/_version.py at the accepted commit says {name} = {have}, "
                    f"but the record says {want}."
                )
    text = show("BRAIN.yaml")
    if text is not None:
        m = re.search(r'^version:\s*"?([^"\s]+)"?\s*$', text, re.M)
        have = m.group(1) if m else None
        if have != version:
            problems.append(
                f"BRAIN.yaml at the accepted commit says version {have}, but the record says {version}."
            )
    text = show("README.md")
    if text is not None and version not in text:
        problems.append(
            f"README.md at the accepted commit does not mention version {version}."
        )


def check(repo):
    problems, warnings = [], []
    data = load_record(repo, problems)
    if data is None:
        return problems, warnings
    check_evidence(data, problems)
    revision, version = data.get("revision"), data.get("version")
    if not (isinstance(revision, str) and SHA.match(revision) and isinstance(version, str)):
        return problems, warnings
    code, _, _ = git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
    if code != 0:
        problems.append(
            f"The accepted commit {revision} does not exist in this repository "
            "(if this is a CI run, the checkout needs full history)."
        )
        return problems, warnings
    check_versions_at_commit(repo, revision, version, problems)
    code, out, _ = git(repo, "rev-list", "--count", f"{revision}..HEAD")
    if code == 0 and out.strip().isdigit() and int(out) > STALE_AFTER_COMMITS:
        warnings.append(
            f"Heads up: the code is {int(out)} commits ahead of the accepted commit "
            f"{revision[:12]} (limit {STALE_AFTER_COMMITS}). The release record is getting stale "
            "and should be refreshed. This is a warning only."
        )
    return problems, warnings


def strict_requested(args_strict, env):
    return bool(args_strict) or env.get("RELEASE_GUARD_STRICT", "") not in ("", "0", "false")


def run(repo, strict, env=None):
    """Print results. Returns the exit code: nonzero only in strict mode with problems."""
    import os
    import sys as _sys

    env = os.environ if env is None else env
    problems, warnings = check(repo)
    for w in warnings:
        print("::warning title=Release record is getting stale::" + w)
    for p in problems:
        print(("::error title=Release record mismatch::" if strict else
               "::warning title=Release record mismatch::") + p)
    lines = ["## Release record guard", ""]
    if problems:
        mode = "strict (blocks CI)" if strict else "warn only (does not block CI)"
        lines.append(f"Mode: {mode}. {len(problems)} problem(s) found:")
        lines += [f"- {p}" for p in problems]
    else:
        lines.append("The release record and the code at its accepted commit agree.")
    lines += [f"- Warning: {w}" for w in warnings]
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError:
            pass
    print("\n".join(lines))
    return 1 if (problems and strict) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when problems are found (also RELEASE_GUARD_STRICT=1)")
    args = parser.parse_args(argv)
    import os
    return run(args.repo, strict_requested(args.strict, os.environ))


if __name__ == "__main__":
    sys.exit(main())
