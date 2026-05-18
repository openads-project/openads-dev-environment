#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

"""Generate the template Docker Compose file from the default ROS 2 launch file."""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


DEFAULT_NAMESPACE = "/"
DEFAULT_LAUNCH_FILE_NAME = "lanelet2_route_planning_launch.py"
COMPOSE_PATH = Path("docker/compose/docker-compose.yml")


@dataclass(frozen=True)
class LaunchArgument:
    name: str
    default_value: str
    description: str


@dataclass(frozen=True)
class LaunchData:
    package: str
    executable: str
    launch_file_name: str
    arguments: list[LaunchArgument]
    remappable_topic_names: list[str]


@dataclass(frozen=True)
class PackageMetadata:
    name: str
    version: str


def constant_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def call_keyword(call: ast.Call, keyword_name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def launch_argument_from_call(call: ast.Call) -> LaunchArgument | None:
    if call_name(call.func) != "DeclareLaunchArgument":
        return None
    if not call.args:
        return None

    name = constant_string(call.args[0])
    if name is None:
        return None

    default_value = constant_string(call_keyword(call, "default_value"))
    description = constant_string(call_keyword(call, "description")) or ""
    if default_value is None:
        default_value = ""

    return LaunchArgument(name=name, default_value=default_value, description=description)


def extract_remappable_topic_names(tree: ast.AST) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "remappable_topics" for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            raise ValueError("remappable_topics must be a list of DeclareLaunchArgument calls")

        topic_names: list[str] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Call):
                raise ValueError("remappable_topics entries must be DeclareLaunchArgument calls")
            launch_argument = launch_argument_from_call(element)
            if launch_argument is None:
                raise ValueError("remappable_topics entries must be parseable DeclareLaunchArgument calls")
            topic_names.append(launch_argument.name)
        return topic_names

    raise ValueError("default launch file does not define remappable_topics")


def extract_launch_arguments(tree: ast.AST) -> list[LaunchArgument]:
    arguments: list[LaunchArgument] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        launch_argument = launch_argument_from_call(node)
        if launch_argument is None or launch_argument.name in seen:
            continue
        arguments.append(launch_argument)
        seen.add(launch_argument.name)

    if not arguments:
        raise ValueError("default launch file does not define any DeclareLaunchArgument calls")
    return arguments


def extract_node_data(tree: ast.AST) -> tuple[str, str]:
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and call_name(node.func) == "Node"]
    if len(nodes) != 1:
        raise ValueError(f"default launch file must define exactly one Node call, found {len(nodes)}")

    node = nodes[0]
    package = constant_string(call_keyword(node, "package"))
    executable = constant_string(call_keyword(node, "executable"))
    if package is None or executable is None:
        raise ValueError("Node package and executable must be string literals")
    return package, executable


def parse_launch_file(launch_file: Path) -> LaunchData:
    tree = ast.parse(launch_file.read_text(encoding="utf-8"), filename=str(launch_file))
    package, executable = extract_node_data(tree)
    return LaunchData(
        package=package,
        executable=executable,
        launch_file_name=launch_file.name,
        arguments=extract_launch_arguments(tree),
        remappable_topic_names=extract_remappable_topic_names(tree),
    )


def find_default_launch_file(repo_root: Path, package_name: str) -> Path:
    launch_file = repo_root / package_name / "launch" / DEFAULT_LAUNCH_FILE_NAME
    if not launch_file.is_file():
        raise FileNotFoundError(f"default launch file not found: {launch_file}")
    return launch_file


def parse_package_metadata(package_xml: Path) -> PackageMetadata:
    root = ET.parse(package_xml).getroot()
    name = " ".join(root.findtext("name", default="").split())
    version = " ".join(root.findtext("version", default="").split())
    if not name or not version:
        raise ValueError(f"package.xml must define name and version: {package_xml}")
    return PackageMetadata(name=name, version=version)


def run_git(args: list[str], repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def github_owner_from_origin(repo_root: Path) -> str:
    remote_url = run_git(["remote", "get-url", "origin"], repo_root)
    patterns = (
        r"^git@github\.com:([^/]+)/[^/]+(?:\.git)?$",
        r"^https://github\.com/([^/]+)/[^/]+(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+)/[^/]+(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, remote_url)
        if match:
            return match.group(1)
    raise ValueError(f"origin remote is not a supported GitHub URL: {remote_url}")


def env_name(argument_name: str) -> str:
    return argument_name.upper()


def compose_service_name(package_name: str) -> str:
    return package_name.replace("_", "-")


def sorted_launch_arguments(launch_data: LaunchData) -> dict[str, LaunchArgument]:
    return {argument.name: argument for argument in launch_data.arguments}


def command_argument_names(launch_data: LaunchData) -> list[str]:
    names = ["namespace", "name", "log_level", "use_sim_time", *launch_data.remappable_topic_names]
    return [name for name in names if name in sorted_launch_arguments(launch_data)]


def strip_markdown_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        return value[1:-1]
    return value


def extract_readme_topic_directions(package_readme: Path) -> dict[str, str]:
    if not package_readme.is_file():
        return {}

    directions: dict[str, str] = {}
    current_direction: str | None = None
    for line in package_readme.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "#### Subscribed Topics":
            current_direction = "input"
            continue
        if stripped == "#### Published Topics":
            current_direction = "output"
            continue
        if stripped.startswith("#### "):
            current_direction = None
            continue
        if current_direction is None or not stripped.startswith("|"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in {"Topic", "---"}:
            continue
        topic = strip_markdown_code(cells[0])
        existing_direction = directions.get(topic)
        if existing_direction is not None and existing_direction != current_direction:
            directions[topic] = "other"
            continue
        directions[topic] = current_direction

    return directions


def topic_environment_lines(launch_data: LaunchData, package_readme: Path) -> tuple[list[str], list[str], list[str]]:
    arguments = sorted_launch_arguments(launch_data)
    topic_directions = extract_readme_topic_directions(package_readme)
    input_lines: list[str] = []
    output_lines: list[str] = []
    other_lines: list[str] = []

    for name in launch_data.remappable_topic_names:
        argument = arguments.get(name)
        if argument is None:
            continue
        direction = topic_directions.get(argument.default_value, "other")

        line = f"      {env_name(argument.name)}: {argument.default_value}"
        if direction == "input":
            input_lines.append(line)
        elif direction == "output":
            output_lines.append(line)
        else:
            other_lines.append(line)

    return input_lines, output_lines, other_lines


def build_compose(repo_root: Path) -> str:
    package_metadata = parse_package_metadata(repo_root / "lanelet2_route_planning" / "package.xml")
    launch_data = parse_launch_file(find_default_launch_file(repo_root, package_metadata.name))

    if launch_data.package != package_metadata.name:
        raise ValueError(
            f"default launch package {launch_data.package!r} does not match package.xml name {package_metadata.name!r}"
        )

    owner = github_owner_from_origin(repo_root)
    image = f"ghcr.io/{owner}/{package_metadata.name}:v{package_metadata.version}"
    arguments = sorted_launch_arguments(launch_data)
    input_lines, output_lines, other_lines = topic_environment_lines(launch_data, repo_root / package_metadata.name / "README.md")
    log_level = arguments.get("log_level", LaunchArgument("log_level", "info", "")).default_value or "info"
    use_sim_time = arguments.get("use_sim_time", LaunchArgument("use_sim_time", "false", "")).default_value or "false"
    node_name = arguments.get("name", LaunchArgument("name", launch_data.executable, "")).default_value or launch_data.executable

    lines = [
        "services:",
        "",
        f"  {compose_service_name(package_metadata.name)}:",
        f"    image: {image}",
        "    environment:",
        "      # --- name ------",
        f"      NAMESPACE: {DEFAULT_NAMESPACE}",
        f"      NAME: {node_name}",
    ]
    if input_lines:
        lines.extend(["      # --- inputs ----", *input_lines])
    if output_lines:
        lines.extend(["      # --- outputs ---", *output_lines])
    lines.extend(
        [
            "      # --- other -----",
            *other_lines,
            f"      LOG_LEVEL: ${{LOG_LEVEL:-{log_level}}}",
            f"      USE_SIM_TIME: ${{USE_SIM_TIME:-{use_sim_time}}}",
            "    command:",
            "      - /bin/bash",
            "      - -ic",
            "      - |",
            f"        ros2 launch {launch_data.package} {launch_data.launch_file_name} \\",
        ]
    )

    launch_argument_names = command_argument_names(launch_data)
    for index, argument_name in enumerate(launch_argument_names):
        suffix = " \\" if index < len(launch_argument_names) - 1 else ""
        lines.append(f"          {argument_name}:=$${{{env_name(argument_name)}}}{suffix}")

    lines.extend(
        [
            "    # volumes:",
            "    #   - ./params.yml:"
            f"/docker-ros/ws/install/{package_metadata.name}/share/{package_metadata.name}/config/params.yml",
            "",
        ]
    )
    return "\n".join(lines)


def build_diff(expected: str, current: str, compose_path: Path, repo_root: Path) -> str:
    rel_path = compose_path.relative_to(repo_root).as_posix()
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )


def print_diff(old: str, new: str, compose_path: Path, repo_root: Path) -> None:
    red, green, cyan, reset = "\033[31m", "\033[32m", "\033[36m", "\033[0m"
    diff = build_diff(new, old, compose_path, repo_root)
    if not diff:
        print("(no changes)")
        return

    for line in diff.splitlines(keepends=True):
        if line.startswith("+") and not line.startswith("+++"):
            color = green
        elif line.startswith("-") and not line.startswith("---"):
            color = red
        elif line.startswith("@@"):
            color = cyan
        else:
            color = ""
        print(f"{color}{line}{reset if color else ''}", end="")


def resolve_repo_root(raw_repo_root: str | None) -> Path:
    if raw_repo_root:
        return Path(raw_repo_root).resolve()
    return Path(__file__).resolve().parents[2]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate docker/compose/docker-compose.yml from the default launch file")
    parser.add_argument("repo_root", nargs="?", help="Repository root (defaults to inferred top-level)")
    parser.add_argument("--check", action="store_true", help="Check whether docker compose output is up to date")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    compose_path = repo_root / COMPOSE_PATH

    try:
        expected = build_compose(repo_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        current = compose_path.read_text(encoding="utf-8") if compose_path.exists() else ""
        if current != expected:
            diff = build_diff(expected, current, compose_path, repo_root)
            if diff:
                print(diff, end="" if diff.endswith("\n") else "\n")
            else:
                print(f"{COMPOSE_PATH} is stale", file=sys.stderr)
            return 1
        return 0

    compose_path.parent.mkdir(parents=True, exist_ok=True)
    current = compose_path.read_text(encoding="utf-8") if compose_path.exists() else ""
    compose_path.write_text(expected, encoding="utf-8")
    print(f"Updated {compose_path}")
    print_diff(current, expected, compose_path, repo_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
