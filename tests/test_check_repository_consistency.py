#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path


DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = DEV_ENV_ROOT / "scripts" / "check_repository_consistency.py"


def load_checker():
    """Load the repository consistency checker as a module."""
    spec = importlib.util.spec_from_file_location(
        "check_repository_consistency",
        CHECKER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in a test repository."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_clone_repo_at_head_preserves_source_origin(tmp_path: Path) -> None:
    """Keep the real remote URL when creating a local comparison clone."""
    checker = load_checker()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    expected_origin = "git@github.com:openads-project/example.git"

    source.mkdir()
    run_git(source, "init")
    run_git(source, "config", "user.name", "Consistency Test")
    run_git(source, "config", "user.email", "consistency@example.com")
    run_git(source, "remote", "add", "origin", expected_origin)
    (source / "README.md").write_text("# Example\n")
    run_git(source, "add", "README.md")
    run_git(source, "commit", "-m", "Initial commit")

    assert checker.clone_repo_at_head(source, destination) is None
    assert (
        run_git(destination, "remote", "get-url", "origin").stdout.strip() == expected_origin
    )


def test_print_detail_indents_nested_multiline_items() -> None:
    """Indent outcome entries below their detail heading."""
    checker = load_checker()
    output = io.StringIO()

    with redirect_stdout(output):
        checker.print_detail("Outcome differences:\n- first difference\n- second difference")

    assert output.getvalue() == (
        "  - Outcome differences:\n"
        "    - first difference\n"
        "    - second difference\n"
    )


def test_required_root_ci_workflows_requires_ghcr_cleanup(tmp_path: Path) -> None:
    """Report the GHCR cleanup workflow when it is missing downstream."""
    checker = load_checker()
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    for workflow_name in (
        "compose-oci.yml",
        "consistency.yml",
        "docker-ros.yml",
        "docs.yml",
        "helm-oci.yml",
    ):
        (workflows_dir / workflow_name).touch()

    result = checker.check_required_root_ci_workflows(checker.CheckContext(tmp_path))

    assert not result.passed
    assert result.details == [".github/workflows/ghcr-cleanup.yml"]


def test_root_ci_workflows_matches_ghcr_cleanup_template(tmp_path: Path) -> None:
    """Compare the downstream GHCR cleanup workflow with its template."""
    checker = load_checker()
    workflows_dir = tmp_path / ".github" / "workflows"
    templates_dir = tmp_path / ".openads-dev-environment" / ".github" / "workflow_calls"
    workflows_dir.mkdir(parents=True)
    templates_dir.mkdir(parents=True)
    workflow_names = (
        "compose-oci.yml",
        "consistency.yml",
        "docs.yml",
        "ghcr-cleanup.yml",
        "helm-oci.yml",
    )
    for workflow_name in workflow_names:
        (workflows_dir / workflow_name).write_text("name: workflow\n")
        (templates_dir / workflow_name).write_text("name: workflow\n")
    (templates_dir / "ghcr-cleanup.yml").write_text("name: workflow\nsecrets: inherit\n")

    result = checker.check_root_ci_workflows_match_templates(checker.CheckContext(tmp_path))

    assert not result.passed
    assert len(result.details) == 1
    assert ".github/workflows/ghcr-cleanup.yml" in result.details[0]
