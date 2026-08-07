#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

"""Generate Helm charts from ROS 2 launch files."""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from generate_compose import (
    build_diff,
    build_template_environment,
    command_argument_names,
    compose_service_name,
    container_image_repository,
    DEFAULT_NAMESPACE,
    env_name,
    extra_launch_environment_variables,
    find_compose_launch_files,
    find_default_package_metadata,
    GITLAB_REGISTRY_ENV_NAME,
    installed_params_path,
    launch_file_stem,
    LaunchArgument,
    LaunchCommandArgument,
    LaunchData,
    PackageMetadata,
    parse_launch_file,
    print_diff,
    render_template,
    resolve_repo_root,
    sorted_launch_arguments,
    STANDARD_LAUNCH_ARGUMENT_NAMES,
    topic_environment_variables,
)

HELM_DIR = Path("deployment/helm")
CHART_PATH = HELM_DIR / "Chart.yaml"
VALUES_PATH = HELM_DIR / "values.yaml"


def extract_readme_tagline(readme_path: Path) -> str | None:
    if not readme_path.is_file():
        return None

    match = re.search(r"^\*\*(.+)\*\*\s*$", readme_path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip()


def package_description(package_xml: Path) -> str:
    root = ET.parse(package_xml).getroot()
    return " ".join(root.findtext("description", default="").split())


def chart_description(repo_root: Path, package_name: str) -> str:
    tagline = extract_readme_tagline(repo_root / "README.md")
    if tagline:
        return tagline

    description = package_description(repo_root / package_name / "package.xml")
    if description:
        return description
    raise ValueError("Chart description not found in the top-level README or default package.xml")


def helm_launch_arguments(launch_data: LaunchData, excluded_names: frozenset[str] = frozenset()) -> list[LaunchCommandArgument]:
    arguments = sorted_launch_arguments(launch_data)
    return [
        LaunchCommandArgument(
            name=argument_name,
            env_name=env_name(argument_name),
            only_if_set=arguments[argument_name].default_value == "" and argument_name not in STANDARD_LAUNCH_ARGUMENT_NAMES,
        )
        for argument_name in command_argument_names(launch_data)
        if argument_name not in excluded_names
    ]


def helm_paths_for_launch_files(launch_files: list[Path]) -> dict[Path, tuple[Path, Path]]:
    if len(launch_files) == 1:
        return {launch_files[0]: (CHART_PATH, VALUES_PATH)}

    paths: dict[Path, tuple[Path, Path]] = {}
    used_stems: dict[str, Path] = {}
    for launch_file in launch_files:
        stem = launch_file_stem(launch_file)
        previous = used_stems.get(stem)
        if previous is not None:
            raise ValueError(f"launch file name collision after removing the launch suffix: {previous.name}, {launch_file.name}")
        used_stems[stem] = launch_file
        chart_dir = HELM_DIR / stem
        paths[launch_file] = (chart_dir / "Chart.yaml", chart_dir / "values.yaml")
    return paths


def render_helm(
    repo_root: Path,
    package_metadata: PackageMetadata,
    launch_data: LaunchData,
    image_repository: str,
    *,
    multi_launch: bool,
) -> tuple[str, str]:
    launch_stem = launch_file_stem(Path(launch_data.launch_file_name))
    base_chart_name = compose_service_name(package_metadata.name)
    chart_name = f"{base_chart_name}-{compose_service_name(launch_stem)}" if multi_launch else base_chart_name

    arguments = sorted_launch_arguments(launch_data)
    input_variables, output_variables, other_topic_variables = topic_environment_variables(
        launch_data, repo_root / package_metadata.name / "README.md"
    )
    log_level = arguments.get("log_level", LaunchArgument("log_level", "info", "")).default_value or "info"
    use_sim_time = arguments.get("use_sim_time", LaunchArgument("use_sim_time", "false", "")).default_value or "false"
    if multi_launch:
        node_name = arguments.get("name", LaunchArgument("name", package_metadata.name, "")).default_value
        node_name = node_name or package_metadata.name
        params_argument = arguments.get("params")
        params_default_path = None
        if params_argument is not None:
            params_default_path = params_argument.installed_default_path or params_argument.default_value or None
    else:
        node_name = package_metadata.name
        params_default_path = installed_params_path(package_metadata.name) if "params" in arguments else None

    excluded_launch_arguments = (
        frozenset({"params"}) if multi_launch and "params" in arguments and params_default_path is None else frozenset()
    )

    common_context = {
        "chart_name": chart_name,
        "version": package_metadata.version,
        "description": chart_description(repo_root, package_metadata.name),
        "image": f"{image_repository}:v{package_metadata.version}",
        "namespace": DEFAULT_NAMESPACE,
        "node_name": node_name,
        "input_variables": input_variables,
        "output_variables": output_variables,
        "other_topic_variables": other_topic_variables,
        "extra_launch_variables": extra_launch_environment_variables(launch_data),
        "log_level": log_level,
        "use_sim_time": use_sim_time,
        "params_default_path": params_default_path,
        "launch_package": package_metadata.name,
        "launch_file_name": launch_data.launch_file_name,
        "launch_arguments": helm_launch_arguments(launch_data, excluded_launch_arguments),
    }
    template_env = build_template_environment()
    return (
        render_template(template_env, "helm_chart.yaml.j2", common_context),
        render_template(template_env, "helm_values.yaml.j2", common_context),
    )


def build_helm(repo_root: Path, gitlab_registry: str | None = None) -> dict[Path, str]:
    package_metadata = find_default_package_metadata(repo_root)
    launch_files = find_compose_launch_files(repo_root, package_metadata.name)
    helm_paths = helm_paths_for_launch_files(launch_files)
    multi_launch = len(launch_files) > 1
    image_repository = container_image_repository(repo_root, package_metadata.name, gitlab_registry)

    expected_files: dict[Path, str] = {}
    for launch_file in launch_files:
        chart, values = render_helm(
            repo_root,
            package_metadata,
            parse_launch_file(launch_file),
            image_repository,
            multi_launch=multi_launch,
        )
        chart_path, values_path = helm_paths[launch_file]
        expected_files[chart_path] = chart
        expected_files[values_path] = values
    return expected_files


def managed_helm_paths(repo_root: Path) -> set[Path]:
    helm_dir = repo_root / HELM_DIR
    paths = {path for path in (repo_root / CHART_PATH, repo_root / VALUES_PATH) if path.is_file()}
    if helm_dir.is_dir():
        for chart_dir in helm_dir.iterdir():
            if not chart_dir.is_dir():
                continue
            paths.update(path for path in (chart_dir / "Chart.yaml", chart_dir / "values.yaml") if path.is_file())
    return paths


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Helm charts from ROS 2 launch files")
    parser.add_argument("repo_root", nargs="?", help="Repository root (defaults to inferred top-level)")
    parser.add_argument("--check", action="store_true", help="Check whether Helm chart output is up to date")
    parser.add_argument(
        "--gitlab-registry",
        default=os.environ.get(GITLAB_REGISTRY_ENV_NAME),
        help=(
            "GitLab container registry host, optionally including a port "
            f"(defaults to ${GITLAB_REGISTRY_ENV_NAME}, an existing Compose file, or <gitlab-host>:5050)"
        ),
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    repo_root = resolve_repo_root(args.repo_root)

    try:
        expected_files = build_helm(repo_root, gitlab_registry=args.gitlab_registry)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    expected_paths = {repo_root / relative_path for relative_path in expected_files}
    obsolete_paths = managed_helm_paths(repo_root) - expected_paths

    if args.check:
        stale = False
        for relative_path, expected in sorted(expected_files.items()):
            output_path = repo_root / relative_path
            current = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
            if current == expected:
                continue
            stale = True
            diff = build_diff(expected, current, output_path, repo_root)
            if diff:
                print(diff, end="" if diff.endswith("\n") else "\n")
            else:
                print(f"{relative_path} is stale", file=sys.stderr)
        for output_path in sorted(obsolete_paths):
            stale = True
            current = output_path.read_text(encoding="utf-8")
            diff = build_diff("", current, output_path, repo_root)
            if diff:
                print(diff, end="" if diff.endswith("\n") else "\n")
            else:
                print(f"{output_path.relative_to(repo_root)} is obsolete", file=sys.stderr)
        return 1 if stale else 0

    for relative_path, expected in sorted(expected_files.items()):
        output_path = repo_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        current = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        output_path.write_text(expected, encoding="utf-8")
        print(f"Updated {output_path}")
        print_diff(current, expected, output_path, repo_root)
    for output_path in sorted(obsolete_paths):
        current = output_path.read_text(encoding="utf-8")
        output_path.unlink()
        print(f"Removed obsolete {output_path}")
        print_diff(current, "", output_path, repo_root)
        parent = output_path.parent
        if parent != repo_root / HELM_DIR and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
