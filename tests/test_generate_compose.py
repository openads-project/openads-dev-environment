#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = DEV_ENV_ROOT / "tests" / "generate-compose"
GENERATOR_SCRIPT = DEV_ENV_ROOT / "scripts" / "generate_compose.py"
COMPOSE_PATH = Path("docker/compose/docker-compose.yml")


def load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_compose", GENERATOR_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_launch_file(path: Path, *packages: str) -> None:
    nodes = "\n".join(
        f"        Node(package={package!r}, executable={package!r})," for package in packages
    )
    path.write_text(
        f"""#!/usr/bin/env python3

from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


def generate_launch_description():
    return [
        DeclareLaunchArgument("name", default_value={packages[0]!r}),
{nodes}
    ]
""",
        encoding="utf-8",
    )


def test_find_default_launch_file_prefers_package_name_launch_when_multiple_files_launch_package(
    tmp_path: Path,
) -> None:
    generator = load_generator_module()
    package_name = "sample_pkg"
    launch_dir = tmp_path / package_name / "launch"
    launch_dir.mkdir(parents=True)
    preferred = launch_dir / f"{package_name}_launch.py"
    write_launch_file(preferred, package_name)
    write_launch_file(
        launch_dir / f"{package_name}_with_action_client_launch.py",
        package_name,
        "action_client",
    )

    assert generator.find_default_launch_file(tmp_path, package_name) == preferred


def demo_repositories() -> list[Path]:
    return sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir())


@pytest.mark.parametrize("repo_root", demo_repositories(), ids=lambda path: path.name)
def test_generate_compose_check_matches_checked_in_compose(repo_root: Path) -> None:
    compose_path = repo_root / COMPOSE_PATH
    assert compose_path.is_file(), f"Missing expected compose file: {compose_path}"

    result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--check", str(repo_root)],
        check=False,
        text=True,
        capture_output=True,
        cwd=DEV_ENV_ROOT.parent,
    )

    assert result.returncode == 0, (
        f"{repo_root} does not match {compose_path}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )