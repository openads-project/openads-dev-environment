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
CHART_PATH = Path("deployment/helm/Chart.yaml")
VALUES_PATH = Path("deployment/helm/values.yaml")
MULTI_LAUNCH_FIXTURE = FIXTURES_DIR / "sample_pkg_multi_launch"
GITHUB_HELM_WORKFLOW = DEV_ENV_ROOT / ".github" / "workflows" / "helm-oci.yml"
GITHUB_CLEANUP_WORKFLOW = DEV_ENV_ROOT / ".github" / "workflows" / "ghcr-cleanup.yml"
GITLAB_CI_TEMPLATE = DEV_ENV_ROOT / ".gitlab-ci.template.yml"


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
    chart_paths = sorted((repo_root / "deployment" / "helm").glob("**/Chart.yaml"))
    values_paths = sorted((repo_root / "deployment" / "helm").glob("**/values.yaml"))
    assert chart_paths
    assert len(chart_paths) == len(values_paths)

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
  - repository: oci://ghcr.io/openads-project/openads-helm
    name: openadservice
    version: 1.0.0
"""
    assert (repo_root / VALUES_PATH).read_text(encoding="utf-8") == """\
openadservice:
  name: sample-pkg
  image: ghcr.io/openads-project/sample_pkg:v1.0.0
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
    LOG_LEVEL: info
    USE_SIM_TIME: false
    PARAMS: /docker-ros/ws/install/sample_pkg/share/sample_pkg/config/params.yml
  args:
  - /bin/bash
  - -ic
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
  rosParamFileMountPath: /docker-ros/ws/install/sample_pkg/share/sample_pkg/config/params.yml
  rosParamFileData: null
"""


def test_generate_helm_creates_launch_specific_charts(tmp_path: Path) -> None:
    repo_root = prepare_repository(MULTI_LAUNCH_FIXTURE, tmp_path)

    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr

    helm_dir = repo_root / "deployment" / "helm"
    first_chart = (helm_dir / "first_node" / "Chart.yaml").read_text(encoding="utf-8")
    first_values = (helm_dir / "first_node" / "values.yaml").read_text(encoding="utf-8")
    second_chart = (helm_dir / "second_node" / "Chart.yaml").read_text(encoding="utf-8")
    second_values = (helm_dir / "second_node" / "values.yaml").read_text(encoding="utf-8")

    assert "name: sample-pkg-multi-launch\n" in first_chart
    assert "name: sample-pkg-multi-launch\n" in second_chart
    assert "version: 1.0.0-first-node\n" in first_chart
    assert "version: 1.0.0-second-node\n" in second_chart
    assert "appVersion: 1.0.0\n" in first_chart
    assert "appVersion: 1.0.0\n" in second_chart
    assert "NAME: first_node\n" in first_values
    assert "config/params.first_node.yml\n" in first_values
    assert "ros2 launch sample_pkg_multi_launch first_node.launch.py" in first_values
    assert "NAME: second_node\n" in second_values
    assert "PARAMS:" not in second_values
    assert "params:=" not in second_values
    assert "ros2 launch sample_pkg_multi_launch second_node_launch.py" in second_values
    assert not (helm_dir / "Chart.yaml").exists()


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


def test_generate_helm_reports_and_removes_obsolete_managed_chart(tmp_path: Path) -> None:
    repo_root = prepare_repository(MULTI_LAUNCH_FIXTURE, tmp_path)
    result = run_generator(repo_root)
    assert result.returncode == 0, result.stderr

    obsolete_chart_dir = repo_root / "deployment" / "helm" / "obsolete"
    obsolete_chart_dir.mkdir()
    obsolete_chart = obsolete_chart_dir / "Chart.yaml"
    obsolete_values = obsolete_chart_dir / "values.yaml"
    obsolete_chart.write_text("name: obsolete\n", encoding="utf-8")
    obsolete_values.write_text("obsolete: true\n", encoding="utf-8")

    check_result = run_generator(repo_root, "--check")
    assert check_result.returncode == 1
    assert "helm/obsolete/Chart.yaml" in check_result.stdout
    assert "helm/obsolete/values.yaml" in check_result.stdout

    generate_result = run_generator(repo_root)
    assert generate_result.returncode == 0
    assert not obsolete_chart_dir.exists()


def test_helm_oci_workflows_discover_and_publish_multiple_charts() -> None:
    github_workflow = GITHUB_HELM_WORKFLOW.read_text(encoding="utf-8")
    gitlab_ci = GITLAB_CI_TEMPLATE.read_text(encoding="utf-8")
    cleanup_workflow = GITHUB_CLEANUP_WORKFLOW.read_text(encoding="utf-8")

    for workflow in (github_workflow, gitlab_ci):
        assert "find deployment/helm -mindepth 2 -maxdepth 2 -type f -name Chart.yaml" in workflow

    assert "chart-folder: ${{ fromJSON(needs.helm-charts.outputs.chart-folders) }}" in github_workflow
    assert "chart-folder: ${{ matrix.chart-folder }}" in github_workflow
    assert "uses: bsord/helm-push@" in github_workflow
    assert "force: true" in github_workflow

    assert "for chart_folder in" in gitlab_ci
    assert "helm dependency update" in gitlab_ci
    assert "helm package" in gitlab_ci
    assert "helm push" in gitlab_ci

    assert "helm_chart_name=" in cleanup_workflow
    assert "packages: ${{ github.event.repository.name }}/helm/${{ steps.package.outputs.helm_chart_name }}" in cleanup_workflow
    assert "helm_exclude_tags=" in cleanup_workflow
    assert "exclude-tags: ${{ steps.package.outputs.helm_exclude_tags }}" in cleanup_workflow
    assert "helm_packages=" not in cleanup_workflow
