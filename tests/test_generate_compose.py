#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = DEV_ENV_ROOT / "tests" / "generate-compose"
GENERATOR_SCRIPT = DEV_ENV_ROOT / "scripts" / "generate_compose.py"
COMPOSE_DIR = Path("deployment/compose")
GITLAB_CI_TEMPLATE = DEV_ENV_ROOT / ".gitlab-ci.template.yml"
GITHUB_COMPOSE_WORKFLOW = DEV_ENV_ROOT / ".github" / "workflows" / "compose-oci.yml"
MULTI_LAUNCH_FIXTURE = FIXTURES_DIR / "sample_pkg_multi_launch"
GENERATOR_SPEC = importlib.util.spec_from_file_location("compose_generator_under_test", GENERATOR_SCRIPT)
assert GENERATOR_SPEC is not None and GENERATOR_SPEC.loader is not None
GENERATOR_MODULE = importlib.util.module_from_spec(GENERATOR_SPEC)
sys.modules[GENERATOR_SPEC.name] = GENERATOR_MODULE
GENERATOR_SPEC.loader.exec_module(GENERATOR_MODULE)


def demo_repositories() -> list[Path]:
    return sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir())


def initialize_fixture_git(repo_root: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(repo_root)], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "remote", "add", "origin", "https://github.com/openads-project/fixture.git"],
        check=True,
    )


@pytest.mark.parametrize("repo_root", demo_repositories(), ids=lambda path: path.name)
def test_generate_compose_check_matches_checked_in_compose(repo_root: Path) -> None:
    compose_paths = sorted((repo_root / COMPOSE_DIR).glob("docker-compose*.yml"))
    assert compose_paths, f"Missing expected Compose files below: {repo_root / COMPOSE_DIR}"

    result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--check", str(repo_root)],
        check=False,
        text=True,
        capture_output=True,
        cwd=DEV_ENV_ROOT.parent,
    )

    assert result.returncode == 0, (
        f"{repo_root} does not match its checked-in Compose files\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_multi_launch_fixture_uses_abstract_launch_specific_outputs() -> None:
    compose_dir = MULTI_LAUNCH_FIXTURE / COMPOSE_DIR
    first_compose = (compose_dir / "docker-compose.first_node.yml").read_text(encoding="utf-8")
    second_compose = (compose_dir / "docker-compose.second_node.yml").read_text(encoding="utf-8")

    assert {path.name for path in compose_dir.glob("docker-compose*.yml")} == {
        "docker-compose.first_node.yml",
        "docker-compose.second_node.yml",
    }
    assert "NAME: first_node" in first_compose
    assert "config/params.first_node.yml}" in first_compose
    assert "ros2 launch sample_pkg_multi_launch first_node.launch.py" in first_compose
    assert "NAME: second_node" in second_compose
    assert "PARAMS:" not in second_compose
    assert "params:=" not in second_compose
    assert "ros2 launch sample_pkg_multi_launch second_node_launch.py" in second_compose
    assert "combined.launch.py" not in first_compose + second_compose


def test_generator_reports_and_removes_obsolete_managed_compose(tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_pkg"
    shutil.copytree(FIXTURES_DIR / "sample_pkg", repo_root)
    initialize_fixture_git(repo_root)
    obsolete_path = repo_root / COMPOSE_DIR / "docker-compose.obsolete.yml"
    obsolete_path.write_text("services: {}\n", encoding="utf-8")

    check_result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--check", str(repo_root)],
        check=False,
        text=True,
        capture_output=True,
        cwd=DEV_ENV_ROOT.parent,
    )
    assert check_result.returncode == 1
    assert "docker-compose.obsolete.yml" in check_result.stdout

    generate_result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), str(repo_root)],
        check=False,
        text=True,
        capture_output=True,
        cwd=DEV_ENV_ROOT.parent,
    )
    assert generate_result.returncode == 0
    assert not obsolete_path.exists()


def test_generator_rejects_multi_launch_name_collisions() -> None:
    with pytest.raises(ValueError, match="launch file name collision"):
        GENERATOR_MODULE.compose_paths_for_launch_files([Path("duplicate.launch.py"), Path("duplicate_launch.py")])


def test_oci_workflows_derive_sorted_multi_launch_suffix_tags() -> None:
    gitlab_ci = GITLAB_CI_TEMPLATE.read_text(encoding="utf-8")
    github_workflow = GITHUB_COMPOSE_WORKFLOW.read_text(encoding="utf-8")

    for workflow in (gitlab_ci, github_workflow):
        assert "find deployment/compose -maxdepth 1 -type f -name 'docker-compose.*.yml'" in workflow
        assert "| sort" in workflow
        assert "suffix=${filename#docker-compose.}" in workflow
        assert "suffix=${suffix%.yml}" in workflow

    assert 'artifact_tag="$COMPOSE_IMAGE_TAG-$suffix"' in gitlab_ci
    assert 'artifact_tag="${IMAGE_TAG}-${suffix}"' in github_workflow
    assert "multi-launch" not in github_workflow
