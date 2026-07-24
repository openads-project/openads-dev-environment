#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = DEV_ENV_ROOT / "tests" / "generate-compose"
GENERATOR_SCRIPT = DEV_ENV_ROOT / "scripts" / "generate_helm.py"
CHART_PATH = Path("helm/Chart.yaml")
VALUES_PATH = Path("helm/values.yaml")


def demo_repositories() -> list[Path]:
    return sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir())


def prepare_repository(source: Path, destination: Path) -> Path:
    repo_root = destination / source.name
    shutil.copytree(source, repo_root)
    (repo_root / "README.md").write_text(
        f"# {source.name}\n\n**Helm chart for {source.name}**\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"git@github.com:openads-project/{source.name}.git"],
        cwd=repo_root,
        check=True,
    )
    return repo_root


def run_generator(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), *args, str(repo_root)],
        check=False,
        text=True,
        capture_output=True,
        cwd=DEV_ENV_ROOT.parent,
    )


@pytest.mark.parametrize("source", demo_repositories(), ids=lambda path: path.name)
def test_generate_helm_is_idempotent_for_compose_fixtures(source: Path, tmp_path: Path) -> None:
    repo_root = prepare_repository(source, tmp_path)

    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr
    assert (repo_root / CHART_PATH).is_file()
    assert (repo_root / VALUES_PATH).is_file()

    check_result = run_generator(repo_root, "--check")
    assert check_result.returncode == 0, (
        f"Generated chart for {source.name} is not idempotent\n"
        f"stdout:\n{check_result.stdout}\n"
        f"stderr:\n{check_result.stderr}"
    )


def test_generate_helm_matches_expected_chart(tmp_path: Path) -> None:
    repo_root = prepare_repository(FIXTURES_DIR / "sample_pkg", tmp_path)

    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr

    assert (repo_root / CHART_PATH).read_text(encoding="utf-8") == """\
apiVersion: v2
name: sample-pkg
version: 1.0.0
appVersion: 1.0.0
description: Helm chart for sample_pkg
dependencies:
  - repository: oci://ghcr.io/openads-project/openadservice-helm
    name: openadservice
    version: 1.0.0
"""
    assert (repo_root / VALUES_PATH).read_text(encoding="utf-8") == """\
its-module:
  name: sample-pkg
  imageName: ghcr.io/openads-project/sample_pkg
  imageTag: v1.0.0
  command:
  - /bin/bash
  - -ic
  args:
  - |
    ros2 launch sample_pkg sample_pkg_launch.py \\
      namespace:=${NAMESPACE} \\
      name:=${NAME} \\
      log_level:=${LOG_LEVEL} \\
      use_sim_time:=${USE_SIM_TIME} \\
      params:=${PARAMS} \\
      input_topic:=${INPUT_TOPIC} \\
      output_topic:=${OUTPUT_TOPIC} \\
      service_topic:=${SERVICE_TOPIC}
  env:
    # --- name ------
    NAMESPACE: /
    NAME: sample_pkg
    # --- inputs ----
    INPUT_TOPIC: ~/input
    # --- outputs ---
    OUTPUT_TOPIC: ~/output
    # --- other -----
    SERVICE_TOPIC: ~/service
    LOG_LEVEL: ${LOG_LEVEL:-info}
    USE_SIM_TIME: ${USE_SIM_TIME:-false}
    PARAMS: ${PARAMS:-/docker-ros/ws/install/sample_pkg/share/sample_pkg/config/params.yml}
  rosParamFileMountPath: /docker-ros/ws/install/sample_pkg/share/sample_pkg/config/params.yml
  rosParamFileData: null
"""


def test_generate_helm_falls_back_to_package_description(tmp_path: Path) -> None:
    repo_root = prepare_repository(FIXTURES_DIR / "sample_pkg", tmp_path)
    (repo_root / "README.md").unlink()

    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr
    assert "description: Sample package\n" in (repo_root / CHART_PATH).read_text(encoding="utf-8")


def test_generate_helm_check_reports_stale_file_without_rewriting(tmp_path: Path) -> None:
    repo_root = prepare_repository(FIXTURES_DIR / "sample_pkg", tmp_path)
    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr

    values_path = repo_root / VALUES_PATH
    values_path.write_text("stale\n", encoding="utf-8")

    check_result = run_generator(repo_root, "--check")
    assert check_result.returncode == 1
    assert "helm/values.yaml" in check_result.stdout
    assert values_path.read_text(encoding="utf-8") == "stale\n"
