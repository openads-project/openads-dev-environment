#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = DEV_ENV_ROOT / "tests" / "generate-compose"
GENERATOR_SCRIPT = DEV_ENV_ROOT / "scripts" / "generate_compose.py"
COMPOSE_PATH = Path("docker/compose/docker-compose.yml")


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