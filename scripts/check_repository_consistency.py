#!/usr/bin/env python3
"""Repository consistency checks.

Usage:
    python3 .openads-dev-environment/scripts/check_repository_consistency.py \
        [--repo-root PATH] [--only ID[,ID...]] [--skip ID[,ID...]]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    name: str
    passed: bool
    message: str
    details: list[str]


@dataclass(frozen=True)
class CheckContext:
    repo_root: Path


CheckFn = Callable[[CheckContext], CheckResult]


CPP_EXTENSIONS = (".hpp", ".h", ".cpp", ".cc", ".cxx")
PYTHON_EXTENSION = ".py"

RE_CPP_NODE_PUBLIC = re.compile(r"public\s+rclcpp::Node")
RE_CPP_NODE_BASE_INIT = re.compile(r":\s*Node\s*\(")
RE_CPP_DECLARE_AND_LOAD = re.compile(r"\bdeclareAndLoadParameter\b")

RE_PY_NODE_CLASS = re.compile(r"class\s+\w+\s*\(([^)]*\bNode\b[^)]*)\)\s*:")
RE_PY_RCLPY_HINT = re.compile(r"\brclpy\b")
RE_PY_DECLARE_AND_LOAD = re.compile(r"def\s+declare_and_load_parameter\s*\(")

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_status_porcelain(repo_root: Path) -> list[str]:
    status = run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_root)
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    return sorted(lines)


def discover_ros_package_dirs(repo_root: Path) -> list[Path]:
    package_dirs: list[Path] = []
    for pkg_xml in sorted(repo_root.rglob("package.xml")):
        if pkg_xml.parent == repo_root:
            continue
        package_dirs.append(pkg_xml.parent)
    return package_dirs


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def has_cpp_node_evidence(text: str) -> bool:
    return bool(RE_CPP_NODE_PUBLIC.search(text) or RE_CPP_NODE_BASE_INIT.search(text))


def check_no_top_level_package_xml(ctx: CheckContext) -> CheckResult:
    pkg_xml = ctx.repo_root / "package.xml"
    if pkg_xml.exists():
        return CheckResult(
            check_id="no_top_level_package_xml",
            name="No top-level package.xml",
            passed=False,
            message=f"Top-level package.xml exists: {pkg_xml.resolve()}",
            details=[str(pkg_xml.resolve())],
        )

    return CheckResult(
        check_id="no_top_level_package_xml",
        name="No top-level package.xml",
        passed=True,
        message="No package.xml found on repository top-level",
        details=[],
    )


def check_ros_nodes_have_parameter_loader(ctx: CheckContext) -> CheckResult:
    offending: list[str] = []

    for pkg_dir in discover_ros_package_dirs(ctx.repo_root):
        cpp_files = sorted([p for p in pkg_dir.rglob("*") if p.suffix in CPP_EXTENSIONS and p.is_file()])
        py_files = sorted([p for p in pkg_dir.rglob("*") if p.suffix == PYTHON_EXTENSION and p.is_file()])

        cpp_texts: dict[Path, str] = {path: read_text(path) for path in cpp_files}

        cpp_symbol_files = {
            path for path, text in cpp_texts.items() if RE_CPP_DECLARE_AND_LOAD.search(text)
        }

        for path, text in cpp_texts.items():
            if not has_cpp_node_evidence(text):
                continue

            if path in cpp_symbol_files:
                continue

            stem_matches = [cand for cand in cpp_symbol_files if cand.stem == path.stem]
            if stem_matches:
                continue

            offending.append(str(path.relative_to(ctx.repo_root)))

        for path in py_files:
            text = read_text(path)
            if not RE_PY_RCLPY_HINT.search(text):
                continue
            if not RE_PY_NODE_CLASS.search(text):
                continue
            if not RE_PY_DECLARE_AND_LOAD.search(text):
                offending.append(str(path.relative_to(ctx.repo_root)))

    if offending:
        return CheckResult(
            check_id="ros_nodes_have_parameter_loader",
            name="ROS nodes define parameter loader helper",
            passed=False,
            message=(
                "Some ROS node files do not provide required parameter loader "
                "function (declareAndLoadParameter / declare_and_load_parameter)"
            ),
            details=sorted(offending),
        )

    return CheckResult(
        check_id="ros_nodes_have_parameter_loader",
        name="ROS nodes define parameter loader helper",
        passed=True,
        message="All detected ROS node files provide required parameter loader helper",
        details=[],
    )


def check_required_top_level_symlinks(ctx: CheckContext) -> CheckResult:
    expected_links = {
        ".devcontainer": ".openads-dev-environment/.devcontainer/",
        ".vscode": ".openads-dev-environment/.vscode/",
        ".pre-commit-config.yaml": ".openads-dev-environment/.pre-commit-config.yaml",
    }

    errors: list[str] = []

    for link_name, expected_target in expected_links.items():
        link_path = ctx.repo_root / link_name

        if not link_path.exists() and not link_path.is_symlink():
            errors.append(f"{link_name}: missing")
            continue

        if not link_path.is_symlink():
            errors.append(f"{link_name}: exists but is not a symlink")
            continue

        actual_target = os.readlink(link_path)
        if actual_target != expected_target:
            errors.append(
                f"{link_name}: target mismatch (expected '{expected_target}', got '{actual_target}')"
            )

    if errors:
        return CheckResult(
            check_id="required_top_level_symlinks",
            name="Required top-level symlinks",
            passed=False,
            message="Required top-level symlinks are missing or incorrect",
            details=errors,
        )

    return CheckResult(
        check_id="required_top_level_symlinks",
        name="Required top-level symlinks",
        passed=True,
        message="All required top-level symlinks exist with exact targets",
        details=[],
    )


def check_required_root_ci_workflows(ctx: CheckContext) -> CheckResult:
    required_workflows = (
        "docker-ros.yml",
        "docs.yml",
        "industrial_ci.yml",
        "consistency.yml",
    )
    workflows_dir = ctx.repo_root / ".github" / "workflows"

    missing = [
        str((workflows_dir / workflow).relative_to(ctx.repo_root))
        for workflow in required_workflows
        if not (workflows_dir / workflow).is_file()
    ]

    if missing:
        return CheckResult(
            check_id="required_root_ci_workflows",
            name="Required root CI workflow files",
            passed=False,
            message="Required root CI workflow files are missing",
            details=missing,
        )

    return CheckResult(
        check_id="required_root_ci_workflows",
        name="Required root CI workflow files",
        passed=True,
        message="All required root CI workflow files are present",
        details=[],
    )


def check_root_ci_workflows_match_templates(ctx: CheckContext) -> CheckResult:
    workflow_files = (
        "docs.yml",
        "industrial_ci.yml",
        "consistency.yml",
    )
    root_workflows_dir = ctx.repo_root / ".github" / "workflows"
    template_workflows_dir = (
        ctx.repo_root / ".openads-dev-environment" / ".github" / "workflow_calls"
    )

    errors: list[str] = []
    for workflow_name in workflow_files:
        root_path = root_workflows_dir / workflow_name
        template_path = template_workflows_dir / workflow_name

        if not root_path.is_file():
            errors.append(f"missing root workflow: {root_path.relative_to(ctx.repo_root)}")
            continue
        if not template_path.is_file():
            errors.append(f"missing workflow template: {template_path.relative_to(ctx.repo_root)}")
            continue

        if root_path.read_bytes() != template_path.read_bytes():
            errors.append(
                "content mismatch: "
                f"{root_path.relative_to(ctx.repo_root)} != {template_path.relative_to(ctx.repo_root)}"
            )

    if errors:
        return CheckResult(
            check_id="root_ci_workflows_match_templates",
            name="Root CI workflows match workflow_call templates",
            passed=False,
            message=(
                "Root CI workflows (excluding docker-ros.yml) do not exactly match "
                "workflow_call templates"
            ),
            details=errors,
        )

    return CheckResult(
        check_id="root_ci_workflows_match_templates",
        name="Root CI workflows match workflow_call templates",
        passed=True,
        message=(
            "Root CI workflows (excluding docker-ros.yml) exactly match "
            "workflow_call templates"
        ),
        details=[],
    )


def check_dev_environment_at_remote_main(ctx: CheckContext) -> CheckResult:
    submodule_dir = ctx.repo_root / ".openads-dev-environment"

    if not submodule_dir.exists() or not submodule_dir.is_dir():
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message=".openads-dev-environment directory is missing",
            details=[str(submodule_dir)],
        )

    git_dir_check = run_git(["rev-parse", "--git-dir"], cwd=submodule_dir)
    if git_dir_check.returncode != 0:
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message=".openads-dev-environment is not a git repository",
            details=[git_dir_check.stderr.strip() or "git metadata missing"],
        )

    local_head = run_git(["rev-parse", "HEAD"], cwd=submodule_dir)
    if local_head.returncode != 0:
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message="Failed to resolve local .openads-dev-environment HEAD",
            details=[local_head.stderr.strip() or "unknown error"],
        )

    remote_main = run_git(["ls-remote", "origin", "refs/heads/main"], cwd=submodule_dir)
    if remote_main.returncode != 0:
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message="Failed to query remote origin/main for .openads-dev-environment",
            details=[remote_main.stderr.strip() or "unknown error"],
        )

    remote_line = remote_main.stdout.strip().splitlines()
    if not remote_line:
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message="Remote origin/main ref was not found",
            details=["git ls-remote returned no refs for refs/heads/main"],
        )

    remote_hash = remote_line[0].split()[0]
    local_hash = local_head.stdout.strip()

    if local_hash != remote_hash:
        return CheckResult(
            check_id="dev_environment_at_remote_main",
            name=".openads-dev-environment matches origin/main",
            passed=False,
            message="Submodule HEAD does not match remote origin/main",
            details=[f"local HEAD : {local_hash}", f"origin/main: {remote_hash}"],
        )

    return CheckResult(
        check_id="dev_environment_at_remote_main",
        name=".openads-dev-environment matches origin/main",
        passed=True,
        message="Submodule HEAD matches remote origin/main",
        details=[],
    )


def check_readme_generator_is_idempotent(ctx: CheckContext) -> CheckResult:
    generator_script = ctx.repo_root / ".openads-dev-environment" / "scripts" / "generate_readme.py"
    if not generator_script.exists():
        return CheckResult(
            check_id="readme_generator_is_idempotent",
            name="README generator produces no git changes",
            passed=False,
            message="README generator script is missing",
            details=[str(generator_script)],
        )

    try:
        before = git_status_porcelain(ctx.repo_root)
    except RuntimeError as err:
        return CheckResult(
            check_id="readme_generator_is_idempotent",
            name="README generator produces no git changes",
            passed=False,
            message="Failed to snapshot git status before running README generator",
            details=[str(err)],
        )

    run_result = run_command(
        [sys.executable, str(generator_script), str(ctx.repo_root)],
        cwd=ctx.repo_root,
    )
    if run_result.returncode != 0:
        details: list[str] = [f"exit code: {run_result.returncode}"]
        if run_result.stderr.strip():
            details.append(f"stderr: {run_result.stderr.strip()}")
        if run_result.stdout.strip():
            details.append(f"stdout: {run_result.stdout.strip()}")
        return CheckResult(
            check_id="readme_generator_is_idempotent",
            name="README generator produces no git changes",
            passed=False,
            message="README generator execution failed",
            details=details,
        )

    try:
        after = git_status_porcelain(ctx.repo_root)
    except RuntimeError as err:
        return CheckResult(
            check_id="readme_generator_is_idempotent",
            name="README generator produces no git changes",
            passed=False,
            message="Failed to snapshot git status after running README generator",
            details=[str(err)],
        )

    if before != after:
        before_set = set(before)
        after_set = set(after)
        added = sorted(after_set - before_set)
        removed = sorted(before_set - after_set)
        details = []
        if added:
            details.append("Added git status entries:")
            details.extend([f"+ {line}" for line in added])
        if removed:
            details.append("Removed git status entries:")
            details.extend([f"- {line}" for line in removed])
        return CheckResult(
            check_id="readme_generator_is_idempotent",
            name="README generator produces no git changes",
            passed=False,
            message="Running README generator changed git status",
            details=details or ["git status changed (unable to compute detailed diff)"],
        )

    return CheckResult(
        check_id="readme_generator_is_idempotent",
        name="README generator produces no git changes",
        passed=True,
        message="README generator did not change git status",
        details=[],
    )


CHECKS: dict[str, tuple[str, CheckFn]] = {
    "no_top_level_package_xml": ("No top-level package.xml", check_no_top_level_package_xml),
    "ros_nodes_have_parameter_loader": (
        "ROS nodes define parameter loader helper",
        check_ros_nodes_have_parameter_loader,
    ),
    "required_top_level_symlinks": (
        "Required top-level symlinks",
        check_required_top_level_symlinks,
    ),
    "required_root_ci_workflows": (
        "Required root CI workflow files",
        check_required_root_ci_workflows,
    ),
    "root_ci_workflows_match_templates": (
        "Root CI workflows match workflow_call templates",
        check_root_ci_workflows_match_templates,
    ),
    "dev_environment_at_remote_main": (
        ".openads-dev-environment matches origin/main",
        check_dev_environment_at_remote_main,
    ),
    "readme_generator_is_idempotent": (
        "README generator produces no git changes",
        check_readme_generator_is_idempotent,
    ),
}


def parse_csv_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    if cli_repo_root:
        return Path(cli_repo_root).resolve()

    script_path = Path(__file__).resolve()
    # .../<repo>/.openads-dev-environment/scripts/check_repository_consistency.py
    return script_path.parents[2]


def resolve_selected_checks(only: set[str], skip: set[str]) -> tuple[list[str], str | None]:
    known = set(CHECKS.keys())

    unknown_only = sorted(only - known)
    unknown_skip = sorted(skip - known)
    if unknown_only or unknown_skip:
        parts = []
        if unknown_only:
            parts.append(f"Unknown --only check id(s): {', '.join(unknown_only)}")
        if unknown_skip:
            parts.append(f"Unknown --skip check id(s): {', '.join(unknown_skip)}")
        return [], "\n".join(parts)

    selected = list(CHECKS.keys())
    if only:
        selected = [check_id for check_id in selected if check_id in only]

    if skip:
        selected = [check_id for check_id in selected if check_id not in skip]

    return selected, None


def run_checks(ctx: CheckContext, selected_check_ids: list[str]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check_id in selected_check_ids:
        _, check_fn = CHECKS[check_id]
        results.append(check_fn(ctx))
    return results


def use_color(stream: object) -> bool:
    if os.getenv("NO_COLOR") is not None:
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(callable(isatty) and isatty())


def colorize(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{ANSI_RESET}"


def print_report(ctx: CheckContext, results: list[CheckResult]) -> None:
    colors_enabled = use_color(sys.stdout)

    print(f"Repository consistency check: {ctx.repo_root}")
    print(f"Checks executed: {len(results)}")

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        status_color = ANSI_GREEN if result.passed else ANSI_RED
        colored_status = colorize(status, status_color, colors_enabled)
        print(f"{colored_status:<14} {result.check_id:<36} {result.message}")

    failed = [result for result in results if not result.passed]
    if failed:
        print("\nFailure details:")
        for result in failed:
            colored_check_id = colorize(result.check_id, ANSI_RED, colors_enabled)
            print(f"- {colored_check_id}")
            if result.details:
                for detail in result.details:
                    print(f"  - {detail}")
            else:
                print("  - (no details provided)")

    passed_count = len([result for result in results if result.passed])
    failed_count = len(results) - passed_count
    if failed_count > 0:
        result_prefix = colorize("Result", ANSI_RED, colors_enabled)
    else:
        result_prefix = colorize("Result", ANSI_GREEN, colors_enabled)
    summary = f"{result_prefix}: {passed_count} passed, {failed_count} failed, {len(results)} total"
    if len(results) == 0:
        summary = colorize(summary, ANSI_YELLOW, colors_enabled)
    print(f"\n{summary}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run top-level repository consistency checks")
    parser.add_argument("--repo-root", help="Path to repository root (defaults to inferred top-level)")
    parser.add_argument("--only", help="Comma-separated check IDs to run")
    parser.add_argument("--skip", help="Comma-separated check IDs to skip")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"ERROR: repository root does not exist or is not a directory: {repo_root}", file=sys.stderr)
        return 2

    only = parse_csv_ids(args.only)
    skip = parse_csv_ids(args.skip)
    selected_check_ids, error = resolve_selected_checks(only, skip)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        print(f"Known check IDs: {', '.join(CHECKS.keys())}", file=sys.stderr)
        return 2

    ctx = CheckContext(repo_root=repo_root)
    results = run_checks(ctx, selected_check_ids)
    print_report(ctx, results)

    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
