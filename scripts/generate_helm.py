#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

"""Generate a Helm chart from the default ROS 2 launch file."""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from generate_compose import (
    DEFAULT_NAMESPACE,
    GITLAB_REGISTRY_ENV_NAME,
    STANDARD_LAUNCH_ARGUMENT_NAMES,
    LaunchArgument,
    LaunchCommandArgument,
    build_diff,
    build_template_environment,
    command_argument_names,
    compose_service_name,
    container_image_repository,
    env_name,
    extra_launch_environment_variables,
    find_default_launch_file,
    find_default_package_metadata,
    installed_params_path,
    parse_launch_file,
    print_diff,
    render_template,
    resolve_repo_root,
    sorted_launch_arguments,
    topic_environment_variables,
)

CHART_PATH = Path("helm/Chart.yaml")
VALUES_PATH = Path("helm/values.yaml")


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


def helm_launch_arguments(launch_data) -> list[LaunchCommandArgument]:
    arguments = sorted_launch_arguments(launch_data)
    return [
        LaunchCommandArgument(
            name=argument_name,
            env_name=env_name(argument_name),
            only_if_set=arguments[argument_name].default_value == "" and argument_name not in STANDARD_LAUNCH_ARGUMENT_NAMES,
        )
        for argument_name in command_argument_names(launch_data)
    ]


def build_helm(repo_root: Path, gitlab_registry: str | None = None) -> dict[Path, str]:
    package_metadata = find_default_package_metadata(repo_root)
    launch_data = parse_launch_file(find_default_launch_file(repo_root, package_metadata.name))

    image_repository = container_image_repository(repo_root, package_metadata.name, gitlab_registry)
    arguments = sorted_launch_arguments(launch_data)
    input_variables, output_variables, other_topic_variables = topic_environment_variables(
        launch_data, repo_root / package_metadata.name / "README.md"
    )
    log_level = arguments.get("log_level", LaunchArgument("log_level", "info", "")).default_value or "info"
    use_sim_time = arguments.get("use_sim_time", LaunchArgument("use_sim_time", "false", "")).default_value or "false"
    params_default_path = installed_params_path(package_metadata.name) if "params" in arguments else None

    common_context = {
        "chart_name": compose_service_name(package_metadata.name),
        "version": package_metadata.version,
        "description": chart_description(repo_root, package_metadata.name),
        "image": f"{image_repository}:v{package_metadata.version}",
        "namespace": DEFAULT_NAMESPACE,
        "node_name": package_metadata.name,
        "input_variables": input_variables,
        "output_variables": output_variables,
        "other_topic_variables": other_topic_variables,
        "extra_launch_variables": extra_launch_environment_variables(launch_data),
        "log_level": log_level,
        "use_sim_time": use_sim_time,
        "params_default_path": params_default_path,
        "launch_package": package_metadata.name,
        "launch_file_name": launch_data.launch_file_name,
        "launch_arguments": helm_launch_arguments(launch_data),
    }
    template_env = build_template_environment()
    return {
        CHART_PATH: render_template(template_env, "helm_chart.yaml.j2", common_context),
        VALUES_PATH: render_template(template_env, "helm_values.yaml.j2", common_context),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate helm/Chart.yaml and helm/values.yaml")
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

    if args.check:
        stale = False
        for relative_path, expected in expected_files.items():
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
        return 1 if stale else 0

    for relative_path, expected in expected_files.items():
        output_path = repo_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        current = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        output_path.write_text(expected, encoding="utf-8")
        print(f"Updated {output_path}")
        print_diff(current, expected, output_path, repo_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
