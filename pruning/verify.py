#!/usr/bin/env python3
"""Build a fresh pinned pruning fixture and check a candidate or its tests alone."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


REVISION = "63d9e26c27b9965a78f0d59512a80d84935a7c4b"
REPOSITORY = Path(__file__).resolve().parent.parent
TEST_PATHS = (
    "src/test/regress/sql/partition_prune.sql",
    "src/test/regress/expected/partition_prune.out",
)


def added_expectation_lines(patch):
    active = False
    line = None
    added = set()
    for text in patch.splitlines():
        if text.startswith("diff --git "):
            active = text.endswith(" b/" + TEST_PATHS[1])
            line = None
        elif active and text.startswith("@@"):
            line = int(re.search(r"\+(\d+)", text)[1])
        elif active and line is not None:
            if text.startswith("+"):
                added.add(line)
                line += 1
            elif text.startswith(" "):
                line += 1
    return added


def failed_added_expectations(diff, added):
    active = False
    line = None
    found = []
    for text in diff.splitlines():
        if text.startswith("diff "):
            active = "/expected/partition_prune.out" in text
            line = None
        elif active and text.startswith("@@"):
            line = int(re.search(r"-(\d+)", text)[1])
        elif active and line is not None:
            if text.startswith("-"):
                if line in added:
                    found.append(text[1:].strip())
                line += 1
            elif text.startswith(" "):
                line += 1
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="PostgreSQL Git repository containing the pinned revision")
    parser.add_argument("--work", required=True, type=Path,
                        help="New, non-existing output directory; it will be preserved")
    parser.add_argument("--candidate", required=True,
                        choices=("clean", "defect", "oq8", "oq6e", "oq4e", "glm"))
    parser.add_argument("--tests-only", action="store_true",
                        help="Apply candidate SQL/expected output only, retaining defective C")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true",
                        help="Check revision and patch application without building")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    if args.tests_only and args.candidate in ("clean", "defect"):
        parser.error("--tests-only requires a model candidate")
    if os.geteuid() == 0:
        parser.error("run as an ordinary user; PostgreSQL initdb rejects root")
    source = args.source.resolve()
    work = args.work.resolve()
    found = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", REVISION + "^{commit}"], text=True).strip()
    if found != REVISION:
        raise RuntimeError("source revision mismatch")
    work.mkdir(parents=True, exist_ok=False)
    tree = work / "source"
    build = work / "build"
    tree.mkdir()
    build.mkdir()
    archive = work / "source.tar"
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar",
                    "--output=" + str(archive), REVISION], check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(tree)], check=True)
    archive.unlink()
    # A nested output directory must not inherit an unrelated enclosing Git repo.
    subprocess.run(["git", "init", "--quiet", "--template=", str(tree)], check=True)
    result = {"source_revision": REVISION, "candidate": args.candidate,
              "tests_only": args.tests_only, "prepare_only": args.prepare_only}
    patch_text = ""

    def apply(patch, included=()):
        command = ["git", "apply", "--whitespace=nowarn"]
        command.extend("--include=" + path for path in included)
        subprocess.run([*command, "--check", str(patch)], cwd=tree, check=True)
        subprocess.run([*command, str(patch)], cwd=tree, check=True)

    if args.candidate != "clean":
        apply(REPOSITORY / "patches/fixture.patch")
    if args.candidate not in ("clean", "defect"):
        patch = REPOSITORY / "patches" / (args.candidate + ".patch")
        patch_text = patch.read_text()
        apply(patch, TEST_PATHS if args.tests_only else ())
        if args.tests_only and not added_expectation_lines(patch_text):
            raise RuntimeError("candidate has no added expected-output lines")
    result["patch_application_pass"] = True
    if args.prepare_only:
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0

    def run(name, command, required=True, env=None):
        with (work / (name + ".log")).open("w") as output:
            completed = subprocess.run(command, cwd=build, stdout=output,
                                       stderr=subprocess.STDOUT, env=env)
        result[name + "_exit"] = completed.returncode
        if required and completed.returncode:
            (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            raise RuntimeError(name + " failed; inspect the corresponding log in --work")
        return completed.returncode

    environment = dict(os.environ, CFLAGS="-O0", LANG="C", LC_ALL="C")
    run("configure", [str(tree / "configure"), "--enable-cassert"], env=environment)
    run("build", ["make", "-j" + str(args.jobs)])
    run("install", ["make", "-j" + str(args.jobs), "install",
                    "DESTDIR=" + str(work / "install")])
    spec = importlib.util.spec_from_file_location("pruning_oracle", REPOSITORY / "verify.py")
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    checks = oracle.check(work / "install/usr/local/pgsql/bin")
    result["query_checks"] = checks
    failures = sum(not (item["rows_ok"] and item["pruning_ok"])
                   for item in checks["checks"])
    expected_failures = 8 if args.tests_only or args.candidate == "defect" else 0
    result["query_expectation_pass"] = len(checks["checks"]) == 15 and failures == expected_failures
    regression_exit = run("regression", ["make", "-j" + str(args.jobs), "check"], required=False)
    log = (work / "regression.log").read_text(errors="replace")
    summary = re.findall(r"^# (?:All \d+ tests passed\.|\d+ of \d+ tests failed\.)$", log, re.M)
    result["regression_summary"] = summary[-1] if summary else None
    if args.tests_only:
        diff = build / "src/test/regress/regression.diffs"
        hits = failed_added_expectations(diff.read_text(), added_expectation_lines(patch_text)) if diff.is_file() else []
        result["differing_added_expectation_lines"] = hits
        result["test_sensitivity_pass"] = regression_exit != 0 and bool(hits)
        result["pass"] = result["query_expectation_pass"] and result["test_sensitivity_pass"]
    elif args.candidate == "defect":
        # This control deliberately retains the defect. Report the upstream suite as
        # observed; the negative query oracle defines the control's expected result.
        result["pass"] = result["query_expectation_pass"]
    else:
        result["pass"] = (result["query_expectation_pass"] and regression_exit == 0
                          and result["regression_summary"] == "# All 231 tests passed.")
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
