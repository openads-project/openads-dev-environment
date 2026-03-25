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
COPYRIGHT_HEADER_EXTENSIONS = (".hpp", ".cpp", ".py")

RE_CPP_NODE_PUBLIC = re.compile(r"public\s+rclcpp::Node")
RE_CPP_NODE_BASE_INIT = re.compile(r":\s*Node\s*\(")
RE_CPP_DECLARE_AND_LOAD = re.compile(r"\bdeclareAndLoadParameter\b")

RE_PY_NODE_CLASS = re.compile(r"class\s+\w+\s*\(([^)]*\bNode\b[^)]*)\)\s*:")
RE_PY_RCLPY_HINT = re.compile(r"\brclpy\b")
RE_PY_DECLARE_AND_LOAD = re.compile(r"def\s+declare_and_load_parameter\s*\(")
RE_CPP_STRING_LITERAL = re.compile(r'^(?:u8|u|U|L)?"(?:\\.|[^"\\])*"$')
RE_PY_STRING_LITERAL = re.compile(r"^[rRuUbB]?(?:'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")$")
RE_CMAKE_TARGET_DECL = re.compile(r"^\s*add_(?:executable|library)\s*\(", re.MULTILINE)
RE_COPYRIGHT_HEADER = re.compile(
    r"Copyright\s+Institute\s+for\s+Automotive\s+Engineering\s+\(ika\),\s+RWTH\s+Aachen\s+University"
)
RE_APACHE_SPDX_IDENTIFIER = re.compile(r"SPDX-License-Identifier:\s*Apache-2\.0")
RE_KEYWORD_DEFAULT_VALUE = re.compile(
    r"default_value\s*=\s*([rRuUbB]?(?:'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\"))"
)
RE_LAUNCH_EXECUTABLE = re.compile(r"""executable\s*=\s*["']([^"']+)["']""")

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"

EXPECTED_CMAKE_LINT_LINES = """find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_clang_format_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../.vscode/format/.clang-format)
  set(ament_cmake_clang_tidy_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../.vscode/lint/.clang-tidy)
  set(ament_cmake_flake8_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/../.vscode/lint/ament_flake8.ini)
  ament_lint_auto_find_test_dependencies()"""

EXPECTED_PACKAGEXML_TESTDEPENDS = """  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_cmake_clang_format</test_depend>
  <test_depend>ament_cmake_clang_tidy</test_depend>
  <test_depend>ament_cmake_flake8</test_depend>"""


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


def git_tracked_files(repo_root: Path) -> list[Path]:
    tracked = run_git(["ls-files"], cwd=repo_root)
    if tracked.returncode != 0:
        raise RuntimeError(tracked.stderr.strip() or "git ls-files failed")

    files: list[Path] = []
    for line in tracked.stdout.splitlines():
        if not line.strip():
            continue
        files.append(repo_root / line.strip())
    return files


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


def is_identifier_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def skip_string_literal(text: str, pos: int) -> int:
    quote = text[pos]
    i = pos + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return len(text)


def extract_matching_parenthesized(text: str, open_paren_idx: int) -> tuple[str, int] | None:
    if open_paren_idx >= len(text) or text[open_paren_idx] != "(":
        return None

    depth = 1
    i = open_paren_idx + 1
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"'):
            i = skip_string_literal(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : i], i + 1
        i += 1
    return None


def extract_matching_bracketed(text: str, open_bracket_idx: int) -> tuple[str, int] | None:
    if open_bracket_idx >= len(text) or text[open_bracket_idx] != "[":
        return None

    depth = 1
    i = open_bracket_idx + 1
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"'):
            i = skip_string_literal(text, i)
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[open_bracket_idx + 1 : i], i + 1
        i += 1
    return None


def split_first_argument(call_args: str) -> str | None:
    args = split_top_level_arguments(call_args)
    return args[0] if args else None


def split_top_level_arguments(call_args: str) -> list[str]:
    depth_paren = 0
    depth_bracket = 0
    depth_brace = 0
    depth_angle = 0
    i = 0
    start = 0
    parts: list[str] = []

    while i < len(call_args):
        ch = call_args[i]
        if ch in ("'", '"'):
            i = skip_string_literal(call_args, i)
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        elif ch == "<":
            depth_angle += 1
        elif ch == ">":
            depth_angle = max(0, depth_angle - 1)
        elif (
            ch == ","
            and depth_paren == 0
            and depth_bracket == 0
            and depth_brace == 0
            and depth_angle == 0
        ):
            part = call_args[start:i].strip()
            if part:
                parts.append(part)
            start = i + 1
        i += 1

    tail = call_args[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def find_call_args(text: str, function_name: str) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    search_from = 0
    name_len = len(function_name)

    while True:
        idx = text.find(function_name, search_from)
        if idx < 0:
            break
        search_from = idx + name_len

        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + name_len] if idx + name_len < len(text) else ""
        if (before and is_identifier_char(before)) or (after and is_identifier_char(after)):
            continue

        j = idx + name_len
        while j < len(text) and text[j].isspace():
            j += 1

        # Skip template arguments: create_subscription<MsgT>(...)
        if j < len(text) and text[j] == "<":
            depth = 1
            j += 1
            while j < len(text) and depth > 0:
                ch = text[j]
                if ch in ("'", '"'):
                    j = skip_string_literal(text, j)
                    continue
                if ch == "<":
                    depth += 1
                elif ch == ">":
                    depth -= 1
                j += 1
            while j < len(text) and text[j].isspace():
                j += 1

        if j >= len(text) or text[j] != "(":
            continue

        extracted = extract_matching_parenthesized(text, j)
        if extracted is None:
            continue
        args_text, _ = extracted
        results.append((idx, args_text))

    return results


def unquote_string_literal(literal: str) -> str:
    stripped = literal.strip()
    quote_idx_single = stripped.find("'")
    quote_idx_double = stripped.find('"')
    quote_idx = -1
    quote_char = ""

    if quote_idx_single == -1:
        quote_idx = quote_idx_double
        quote_char = '"'
    elif quote_idx_double == -1:
        quote_idx = quote_idx_single
        quote_char = "'"
    else:
        quote_idx = min(quote_idx_single, quote_idx_double)
        quote_char = stripped[quote_idx]

    if quote_idx < 0:
        return stripped
    end_idx = stripped.rfind(quote_char)
    if end_idx <= quote_idx:
        return stripped
    return stripped[quote_idx + 1 : end_idx]


def collect_literal_comm_names(text: str, call_specs: dict[str, int], *, cpp: bool) -> set[str]:
    literal_matcher = RE_CPP_STRING_LITERAL if cpp else RE_PY_STRING_LITERAL
    topics: set[str] = set()

    for call_name, arg_index in call_specs.items():
        for _, args_text in find_call_args(text, call_name):
            args = split_top_level_arguments(args_text)
            if len(args) <= arg_index:
                continue
            topic_arg = args[arg_index]
            if not literal_matcher.fullmatch(topic_arg):
                continue
            topics.add(unquote_string_literal(topic_arg))
    return topics


def extract_remappable_topics_from_launch(launch_text: str) -> set[str]:
    marker = "remappable_topics"
    marker_idx = launch_text.find(marker)
    if marker_idx < 0:
        return set()

    equal_idx = launch_text.find("=", marker_idx)
    if equal_idx < 0:
        return set()

    bracket_idx = launch_text.find("[", equal_idx)
    if bracket_idx < 0:
        return set()

    extracted = extract_matching_bracketed(launch_text, bracket_idx)
    if extracted is None:
        return set()

    list_body, _ = extracted
    topics: set[str] = set()
    for _, declare_args in find_call_args(list_body, "DeclareLaunchArgument"):
        default_match = RE_KEYWORD_DEFAULT_VALUE.search(declare_args)
        if not default_match:
            continue
        topics.add(unquote_string_literal(default_match.group(1)))
    return topics


def find_node_source_files_for_executable(package_dir: Path, executable: str) -> list[Path]:
    matches: list[Path] = []
    for extension in (".cpp", ".cc", ".cxx", ".py"):
        candidate = package_dir / "src" / f"{executable}{extension}"
        if candidate.is_file():
            matches.append(candidate)
    return matches


def check_ros_pubsub_topics_private_namespace(ctx: CheckContext) -> CheckResult:
    failing_calls: list[str] = []
    cpp_call_specs = {
        "create_publisher": 0,
        "create_subscription": 0,
        "create_service": 0,
        "create_client": 0,
    }
    py_call_specs = {
        "create_publisher": 0,
        "create_subscription": 0,
        "create_service": 1,
        "create_client": 1,
    }

    for pkg_dir in discover_ros_package_dirs(ctx.repo_root):
        cpp_files = sorted([p for p in pkg_dir.rglob("*") if p.suffix in CPP_EXTENSIONS and p.is_file()])
        py_files = sorted([p for p in pkg_dir.rglob("*") if p.suffix == PYTHON_EXTENSION and p.is_file()])

        for path in cpp_files:
            text = read_text(path)
            if not has_cpp_node_evidence(text):
                continue

            for call_name, arg_index in cpp_call_specs.items():
                for call_idx, args_text in find_call_args(text, call_name):
                    args = split_top_level_arguments(args_text)
                    if len(args) <= arg_index:
                        continue
                    topic_arg = args[arg_index]
                    if not RE_CPP_STRING_LITERAL.fullmatch(topic_arg):
                        continue

                    topic_name = unquote_string_literal(topic_arg)
                    if not topic_name.startswith("~/"):
                        line = text.count("\n", 0, call_idx) + 1
                        failing_calls.append(
                            f"{path.relative_to(ctx.repo_root)}:{line} {call_name} topic '{topic_name}'"
                        )

        for path in py_files:
            text = read_text(path)
            if not RE_PY_RCLPY_HINT.search(text) or not RE_PY_NODE_CLASS.search(text):
                continue

            for call_name, arg_index in py_call_specs.items():
                for call_idx, args_text in find_call_args(text, call_name):
                    args = split_top_level_arguments(args_text)
                    if len(args) <= arg_index:
                        continue
                    topic_arg = args[arg_index]
                    if not RE_PY_STRING_LITERAL.fullmatch(topic_arg):
                        continue

                    topic_name = unquote_string_literal(topic_arg)
                    if not topic_name.startswith("~/"):
                        line = text.count("\n", 0, call_idx) + 1
                        failing_calls.append(
                            f"{path.relative_to(ctx.repo_root)}:{line} {call_name} topic '{topic_name}'"
                        )

    if failing_calls:
        return CheckResult(
            check_id="ros_pubsub_topics_private_namespace",
            name="ROS pub/sub topics use private namespace",
            passed=False,
            message=(
                "Some create_publisher/create_subscription/create_service/create_client calls use "
                "string-literal names "
                "outside private namespace '~/...'"
            ),
            details=sorted(failing_calls),
        )

    return CheckResult(
        check_id="ros_pubsub_topics_private_namespace",
        name="ROS pub/sub topics use private namespace",
        passed=True,
        message=(
            "All checkable create_publisher/create_subscription/create_service/create_client "
            "string-literal names "
            "use private namespace '~/...'"
        ),
        details=[],
    )


def check_demo_launch_remappable_topics_cover_node_pubsub(ctx: CheckContext) -> CheckResult:
    package_dir = ctx.repo_root / "ros2_demo_package"
    launch_dir = package_dir / "launch"

    if not launch_dir.is_dir():
        return CheckResult(
            check_id="demo_launch_remappable_topics_cover_node_pubsub",
            name="Demo launch remappable topics cover node pub/sub topics",
            passed=True,
            message="ros2_demo_package/launch not found; nothing to check",
            details=[],
        )

    failures: list[str] = []
    cpp_call_specs = {
        "create_publisher": 0,
        "create_subscription": 0,
        "create_service": 0,
        "create_client": 0,
    }
    py_call_specs = {
        "create_publisher": 0,
        "create_subscription": 0,
        "create_service": 1,
        "create_client": 1,
    }
    launch_files = sorted(launch_dir.glob("*.py"))
    for launch_file in launch_files:
        launch_text = read_text(launch_file)
        remappable_topics = extract_remappable_topics_from_launch(launch_text)
        executables = sorted(set(RE_LAUNCH_EXECUTABLE.findall(launch_text)))

        for executable in executables:
            source_files = find_node_source_files_for_executable(package_dir, executable)
            if not source_files:
                continue

            declared_topics: set[str] = set()
            for source_file in source_files:
                text = read_text(source_file)
                if source_file.suffix == ".py":
                    if not (RE_PY_RCLPY_HINT.search(text) and RE_PY_NODE_CLASS.search(text)):
                        continue
                    declared_topics.update(collect_literal_comm_names(text, py_call_specs, cpp=False))
                    continue

                if has_cpp_node_evidence(text):
                    declared_topics.update(collect_literal_comm_names(text, cpp_call_specs, cpp=True))

            if not declared_topics:
                continue

            if not remappable_topics:
                failures.append(
                    f"{launch_file.relative_to(ctx.repo_root)} ({executable}): "
                    "no remappable_topics defaults found"
                )
                continue

            missing_topics = sorted(topic for topic in declared_topics if topic not in remappable_topics)
            if missing_topics:
                failures.append(
                    f"{launch_file.relative_to(ctx.repo_root)} ({executable}): missing "
                    + ", ".join(missing_topics)
                )

    if failures:
        return CheckResult(
            check_id="demo_launch_remappable_topics_cover_node_pubsub",
            name="Demo launch remappable topics cover node pub/sub topics",
            passed=False,
            message=(
                "Some ros2_demo_package node pub/sub/service names are not listed in launch "
                "remappable_topics"
            ),
            details=failures,
        )

    return CheckResult(
        check_id="demo_launch_remappable_topics_cover_node_pubsub",
        name="Demo launch remappable topics cover node pub/sub topics",
        passed=True,
        message=(
            "All checkable ros2_demo_package node pub/sub/service names are listed in launch "
            "remappable_topics"
        ),
        details=[],
    )


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


def check_top_level_license_apache2(ctx: CheckContext) -> CheckResult:
    license_path = ctx.repo_root / "LICENSE"
    if not license_path.is_file():
        return CheckResult(
            check_id="top_level_license_apache2",
            name='Top-level "LICENSE" with Apache 2.0',
            passed=False,
            message='Top-level "LICENSE" file is missing',
            details=[str(license_path.relative_to(ctx.repo_root))],
        )

    license_text = read_text(license_path)
    required_markers = (
        "Apache License",
        "Version 2.0, January 2004",
        "http://www.apache.org/licenses/",
    )
    missing_markers = [marker for marker in required_markers if marker not in license_text]
    if missing_markers:
        return CheckResult(
            check_id="top_level_license_apache2",
            name='Top-level "LICENSE" with Apache 2.0',
            passed=False,
            message='Top-level "LICENSE" does not appear to contain Apache 2.0 text',
            details=[f"Missing marker: {marker}" for marker in missing_markers],
        )

    return CheckResult(
        check_id="top_level_license_apache2",
        name='Top-level "LICENSE" with Apache 2.0',
        passed=True,
        message='Top-level "LICENSE" exists and contains Apache 2.0 markers',
        details=[],
    )


def check_source_files_have_copyright_notice(ctx: CheckContext) -> CheckResult:
    try:
        tracked_files = git_tracked_files(ctx.repo_root)
    except RuntimeError as err:
        return CheckResult(
            check_id="source_files_have_copyright_notice",
            name="Tracked .cpp/.hpp/.py files include copyright notice",
            passed=False,
            message="Failed to list tracked files from git",
            details=[str(err)],
        )

    offenders: list[str] = []
    for path in tracked_files:
        if path.suffix not in COPYRIGHT_HEADER_EXTENSIONS:
            continue
        if not path.is_file():
            continue

        text = read_text(path)
        header_window = "\n".join(text.splitlines()[:6])
        if not RE_COPYRIGHT_HEADER.search(header_window) or not RE_APACHE_SPDX_IDENTIFIER.search(
            header_window
        ):
            offenders.append(str(path.relative_to(ctx.repo_root)))

    if offenders:
        return CheckResult(
            check_id="source_files_have_copyright_notice",
            name="Tracked .cpp/.hpp/.py files include copyright notice",
            passed=False,
            message=(
                "Some tracked .cpp/.hpp/.py files are missing the required copyright "
                "notice and/or Apache SPDX identifier near the top of the file"
            ),
            details=sorted(offenders),
        )

    return CheckResult(
        check_id="source_files_have_copyright_notice",
        name="Tracked .cpp/.hpp/.py files include copyright notice",
        passed=True,
        message="All tracked .cpp/.hpp/.py files include the required copyright notice",
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


def check_ros_cmake_has_required_lint_block(ctx: CheckContext) -> CheckResult:
    offenders: list[str] = []

    for pkg_dir in discover_ros_package_dirs(ctx.repo_root):
        cmake_lists = pkg_dir / "CMakeLists.txt"
        if not cmake_lists.is_file():
            continue

        cmake_text = read_text(cmake_lists).replace("\r\n", "\n")
        if not RE_CMAKE_TARGET_DECL.search(cmake_text):
            continue

        if EXPECTED_CMAKE_LINT_LINES not in cmake_text:
            offenders.append(str(cmake_lists.relative_to(ctx.repo_root)))

    if offenders:
        return CheckResult(
            check_id="ros_cmake_has_required_lint_block",
            name="ROS CMake packages with targets include required lint block",
            passed=False,
            message=(
                "Some ROS CMake packages with add_executable/add_library targets "
                "do not contain the exact required lint lines"
            ),
            details=sorted(offenders),
        )

    return CheckResult(
        check_id="ros_cmake_has_required_lint_block",
        name="ROS CMake packages with targets include required lint block",
        passed=True,
            message=(
                "All ROS CMake packages with add_executable/add_library targets "
                "contain the exact required lint lines"
            ),
        details=[],
    )


def check_ros_packagexml_has_required_testdepends(ctx: CheckContext) -> CheckResult:
    offenders: list[str] = []

    for pkg_dir in discover_ros_package_dirs(ctx.repo_root):
        package_xml = pkg_dir / "package.xml"
        if not package_xml.is_file():
            continue
        package_xml_text = read_text(package_xml).replace("\r\n", "\n")
        if EXPECTED_PACKAGEXML_TESTDEPENDS not in package_xml_text:
            offenders.append(str(package_xml.relative_to(ctx.repo_root)))

    if offenders:
        return CheckResult(
            check_id="ros_packagexml_has_required_testdepends",
            name="ROS packages include required package.xml test_depend block",
            passed=False,
            message=(
                "Some ROS packages "
                "do not contain the exact required package.xml test_depend lines"
            ),
            details=sorted(offenders),
        )

    return CheckResult(
        check_id="ros_packagexml_has_required_testdepends",
        name="ROS packages include required package.xml test_depend block",
        passed=True,
        message=(
            "All ROS packages "
            "contain the exact required package.xml test_depend lines"
        ),
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
        normalized_actual_target = actual_target.rstrip("/")
        normalized_expected_target = expected_target.rstrip("/")
        if normalized_actual_target != normalized_expected_target:
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
        message="All required top-level symlinks exist with expected targets",
        details=[],
    )


def check_required_root_ci_workflows(ctx: CheckContext) -> CheckResult:
    required_workflows = (
        "docker-ros.yml",
        "docs.yml",
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
    "top_level_license_apache2": (
        'Top-level "LICENSE" with Apache 2.0',
        check_top_level_license_apache2,
    ),
    "source_files_have_copyright_notice": (
        "Tracked .cpp/.hpp/.py files include copyright notice",
        check_source_files_have_copyright_notice,
    ),
    "ros_nodes_have_parameter_loader": (
        "ROS nodes define parameter loader helper",
        check_ros_nodes_have_parameter_loader,
    ),
    "ros_cmake_has_required_lint_block": (
        "ROS CMake packages with targets include required lint block",
        check_ros_cmake_has_required_lint_block,
    ),
    "ros_packagexml_has_required_testdepends": (
        "ROS CMake packages with targets include required package.xml test_depend block",
        check_ros_packagexml_has_required_testdepends,
    ),
    "ros_pubsub_topics_private_namespace": (
        "ROS pub/sub topics use private namespace",
        check_ros_pubsub_topics_private_namespace,
    ),
    "demo_launch_remappable_topics_cover_node_pubsub": (
        "Demo launch remappable topics cover node pub/sub topics",
        check_demo_launch_remappable_topics_cover_node_pubsub,
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
