#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

"""Run the current consistency checker against downstream OpenADS modules.

Usage:
    python3 scripts/check_downstream_consistency.py REPOSITORY_URL [REPOSITORY_URL ...]
    python3 scripts/check_downstream_consistency.py --markdown-report report.md REPOSITORY_URL [...]

The script clones each module into a temporary directory, initializes its
`.openads-dev-environment` submodule, overlays the openads-dev-environment
working tree that contains this script, and runs the overlaid consistency
checker. This makes the script useful both in pull-request CI and for local
validation of unmerged changes.

The overlay copies files into the submodule working tree but does not change the
submodule git HEAD. Therefore the dev_environment_at_remote_main check is skipped
by default: if enabled, it reports whether each module currently pins
origin/main, not whether the overlaid local file contents are current.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


# The script overlays local, possibly unmerged openads-dev-environment files
# into cloned modules. In that mode, this check validates each module's pinned
# submodule HEAD rather than the overlaid files, so it is expected noise for
# validating a local openads-dev-environment branch.
OVERLAY_DEFAULT_SKIP_CHECKS = ("dev_environment_at_remote_main",)


@dataclass(frozen=True)
class ModuleResult:
    """Result of running the consistency checker for one module."""

    repository_url: str
    worktree: Path
    returncode: int
    failed_checks: tuple[str, ...]


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and capture text output."""
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def repository_name(repository_url: str) -> str:
    """Return a filesystem-friendly repository name from a clone URL."""
    name = repository_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    if not name:
        raise ValueError(f"Unable to derive repository name from URL: {repository_url}")
    return name


def git_files(repo_root: Path, include_untracked: bool) -> set[Path]:
    """Return tracked and optionally non-ignored untracked files in a git repo."""
    args = ["git", "ls-files", "-z"]
    if include_untracked:
        args.extend(["--cached", "--modified", "--others", "--exclude-standard"])

    result = run_command(args, repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git ls-files failed in {repo_root}")

    return {
        Path(entry)
        for entry in result.stdout.split("\0")
        if entry
    }


def remove_stale_overlay_files(source_dev_env: Path, target_dev_env: Path) -> None:
    """Remove target files that are tracked there but do not exist in the source."""
    source_tracked = git_files(source_dev_env, include_untracked=False)
    target_tracked = git_files(target_dev_env, include_untracked=False)

    for rel_path in sorted(target_tracked - source_tracked, reverse=True):
        path = target_dev_env / rel_path
        if path.is_file() or path.is_symlink():
            path.unlink()


def overlay_current_dev_environment(source_dev_env: Path, target_dev_env: Path) -> None:
    """Copy the current local dev-environment files into a cloned module."""
    if not target_dev_env.is_dir():
        raise FileNotFoundError(f"Target dev-environment is missing: {target_dev_env}")

    remove_stale_overlay_files(source_dev_env, target_dev_env)

    for rel_path in sorted(git_files(source_dev_env, include_untracked=True)):
        source_path = source_dev_env / rel_path
        target_path = target_dev_env / rel_path
        if source_path.is_dir():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def clone_module(repository_url: str, destination: Path) -> None:
    """Clone an OpenADS module and initialize its submodules."""
    clone_result = run_command(
        ["git", "clone", "--recurse-submodules", "--jobs", "4", repository_url, str(destination)],
        cwd=destination.parent,
    )
    if clone_result.returncode != 0:
        raise RuntimeError(clone_result.stderr.strip() or f"git clone failed for {repository_url}")

    submodule_result = run_command(
        ["git", "submodule", "update", "--init", "--recursive", ".openads-dev-environment"],
        cwd=destination,
    )
    if submodule_result.returncode != 0:
        raise RuntimeError(submodule_result.stderr.strip() or f"submodule init failed for {repository_url}")


def extract_failed_checks(output: str) -> tuple[str, ...]:
    """Return failed consistency check IDs from checker output."""
    failed_checks: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        if not line.startswith("FAIL  "):
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 2 or parts[1] in seen:
            continue
        failed_checks.append(parts[1])
        seen.add(parts[1])
    return tuple(failed_checks)


def run_consistency_check(module_root: Path, checker_args: list[str]) -> tuple[int, tuple[str, ...]]:
    """Run the overlaid consistency checker in a module checkout."""
    checker = module_root / ".openads-dev-environment" / "scripts" / "check_repository_consistency.py"
    command = [sys.executable, str(checker), "--repo-root", str(module_root), *checker_args]
    result = subprocess.run(
        command,
        cwd=module_root,
        check=False,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    return result.returncode, extract_failed_checks(result.stdout)


def test_module(
    repository_url: str,
    work_dir: Path,
    source_dev_env: Path,
    checker_args: list[str],
) -> ModuleResult:
    """Clone, overlay, and run consistency checks for one module."""
    module_root = work_dir / repository_name(repository_url)
    if module_root.exists():
        raise FileExistsError(f"Worktree already exists: {module_root}")

    print(f"\n=== {repository_url} ===", flush=True)
    clone_module(repository_url, module_root)
    overlay_current_dev_environment(source_dev_env, module_root / ".openads-dev-environment")
    returncode, failed_checks = run_consistency_check(module_root, checker_args)
    return ModuleResult(
        repository_url=repository_url,
        worktree=module_root,
        returncode=returncode,
        failed_checks=failed_checks,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test the current openads-dev-environment consistency checker against downstream repositories"
    )
    parser.add_argument(
        "repositories",
        nargs="+",
        help="Repository clone URLs to test",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Directory for cloned repositories. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the temporary work directory after the run.",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        help="Write a concise Markdown report for CI summaries or PR comments.",
    )
    parser.add_argument(
        "--checker-arg",
        action="append",
        default=[],
        help="Additional argument passed to check_repository_consistency.py. Repeat for multiple arguments.",
    )
    parser.add_argument(
        "--include-dev-environment-head-check",
        action="store_true",
        help=(
            "Also run dev_environment_at_remote_main. This reports each module's pinned "
            "submodule commit, even though local dev-environment files are overlaid."
        ),
    )
    return parser.parse_args()


def effective_checker_args(args: argparse.Namespace) -> list[str]:
    """Return checker arguments with overlay-specific defaults applied."""
    checker_args = list(args.checker_arg)
    if args.include_dev_environment_head_check or "--only" in checker_args:
        return checker_args

    skip_value = ",".join(OVERLAY_DEFAULT_SKIP_CHECKS)
    if "--skip" in checker_args:
        skip_index = checker_args.index("--skip")
        if skip_index + 1 >= len(checker_args):
            raise ValueError("--checker-arg --skip must be followed by another --checker-arg value")
        existing_skip = checker_args[skip_index + 1]
        checker_args[skip_index + 1] = f"{existing_skip},{skip_value}" if existing_skip else skip_value
    else:
        checker_args.extend(["--skip", skip_value])
    return checker_args


def markdown_table_cell(value: str) -> str:
    """Escape text for use in a Markdown table cell."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def markdown_link(label: str, url: str) -> str:
    """Return a Markdown link with table-safe label and URL."""
    safe_label = markdown_table_cell(label).replace("[", "\\[").replace("]", "\\]")
    safe_url = url.replace(")", "%29").replace(" ", "%20")
    return f"[{safe_label}]({safe_url})"


def actions_run_url() -> str:
    """Return the current GitHub Actions run URL when running in GitHub Actions."""
    server_url = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not server_url or not repository or not run_id:
        return ""
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def write_markdown_report(results: list[ModuleResult], report_path: Path) -> None:
    """Write a concise Markdown report for downstream consistency results."""
    failed = [result for result in results if result.returncode != 0]
    title = "Downstream consistency check found issues" if failed else "Downstream consistency passed"
    result_text = "found issues" if failed else "passed"
    run_url = actions_run_url()

    lines = [
        f"## {title}",
        "",
        f"The downstream consistency check {result_text}.",
        "",
        "This workflow is intentionally non-blocking.",
    ]
    if run_url:
        lines.append(f"See the full run logs: {run_url}")
    else:
        lines.append("See the full command output for details.")

    lines.extend(
        [
            "",
            "| Repository | Result | Failed checks |",
            "| --- | --- | --- |",
        ]
    )

    for result in results:
        repository = markdown_link(repository_name(result.repository_url), result.repository_url)
        status = "PASS" if result.returncode == 0 else "FAIL"
        failed_checks = ", ".join(f"`{check}`" for check in result.failed_checks)
        if result.returncode != 0 and not failed_checks:
            failed_checks = "See logs"
        lines.append(f"| {repository} | {status} | {failed_checks or '-'} |")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    """Run consistency checks for all requested modules."""
    args = parse_args()
    checker_args = effective_checker_args(args)
    source_dev_env = Path(__file__).resolve().parents[1]

    created_temp_dir = False
    if args.work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="openads-downstream-consistency-"))
        created_temp_dir = True
    else:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using source dev-environment: {source_dev_env}")
    print(f"Using work directory: {work_dir}")

    results: list[ModuleResult] = []
    try:
        for repository_url in args.repositories:
            results.append(test_module(repository_url, work_dir, source_dev_env, checker_args))
    finally:
        if created_temp_dir and args.keep_work_dir:
            print(f"\nKept work directory: {work_dir}")
        elif created_temp_dir:
            shutil.rmtree(work_dir, ignore_errors=True)

    failed = [result for result in results if result.returncode != 0]
    print("\n=== Summary ===")
    for result in results:
        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"{status} {result.repository_url} ({result.worktree})")

    if args.markdown_report:
        write_markdown_report(results, args.markdown_report)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
