# openads-dev-environment

<p align="center">
  <a href="https://github.com/openads-project"><img src="https://img.shields.io/badge/OpenADS-ffff00"/></a>
  <a href="https://github.com/openads-project/openads_ros2_demo_repository/blob/main/LICENSE"><img src="https://img.shields.io/github/license/openads-project/openads_ros2_demo_repository"/></a>
  <a href="https://www.ros.org"><img src="https://img.shields.io/badge/ROS 2-jazzy-22314e"/></a>
</p>

This repository defines a common development environment for components of [🚗 ***OpenADS***](https://github.com/openads-project), the *Open Automated Driving Stack*.


## Installation

1. Add this repository as a Git submodule named `.openads-dev-environment` to the root of any other repository that you would like to use these settings for.
    ```bash
    git submodule add https://github.com/openads-project/openads-dev-environment.git .openads-dev-environment
    ```
2. Create symbolic links to the relevant files and folders.
    ```bash
    ln -s .openads-dev-environment/.vscode .vscode
    ln -s .openads-dev-environment/.devcontainer .devcontainer
    ln -s .openads-dev-environment/.pre-commit-config.yaml .pre-commit-config.yaml
    ```
3. Copy the CI template into your repository. Choose one of the following:

   GitLab:
    ```bash
    cp .openads-dev-environment/.gitlab-ci.template.yml .gitlab-ci.yml
    ```
   GitHub:
    ```bash
    mkdir -p .github/workflows
    cp .openads-dev-environment/.github/workflow_calls/*.yml .github/workflows/
    ```
4. Customize the copied CI definition to fit your repository, in particular `BASE_IMAGE`, `TARGET`, `PLATFORM`, and `COMMAND`.
5. Install the recommended VS Code extensions.  
    > *Ctrl+Shift+P / Extensions: Show Recommended Extensions / Install Workspace Recommended Extensions (Cloud Download Icon)*

## Usage

1. Reopen the repository in a [Dev Container](https://code.visualstudio.com/docs/devcontainers/containers).
    > *Ctrl+Shift+P / Dev Containers: Rebuild and Reopen in Container*
1. Develop and debug your application in a defined development environment with pre-defined settings and configurations, see [.vscode Features](#features).


## Details

This repository contains common development environment configuration, including:
- [.vscode](#vscode) settings, recommended extensions, tasks, and debugging configurations
- [.devcontainer](#devcontainer) definition for developing and debugging in container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros)
- CI templates for [GitLab](.gitlab-ci.template.yml) and [GitHub](.github/workflows/), covering the same `docker-ros`, `repository consistency`, and `documentation` content
- [pre-commit](.pre-commit-config.yaml) configuration for running linting and formatting
- a repository consistency checker script for verifying that consuming repositories follow the expected OpenADS setup

### Repository consistency checks

Use [`scripts/check_repository_consistency.py`](scripts/check_repository_consistency.py) to validate that a repository using this development environment still matches the expected structure and conventions.

```bash
python3 .openads-dev-environment/scripts/check_repository_consistency.py
```

You can limit execution to specific checks with `--only <check_id[,check_id...]>` or skip checks with `--skip <check_id[,check_id...]>`.

| Name | Description |
| --- | --- |
| `no_top_level_package_xml` | Passes when the repository root does not contain a `package.xml`. ROS packages must live in subdirectories instead of treating the whole repository as one package. |
| `top_level_license_apache2` | Passes when a top-level `LICENSE` file exists and contains the Apache 2.0 license text markers (`Apache License`, `Version 2.0, January 2004`, `http://www.apache.org/licenses/`). |
| `source_files_have_copyright_notice` | Passes when every tracked `.cpp`, `.hpp`, and `.py` file contains the required IKA copyright notice and `SPDX-License-Identifier: Apache-2.0` near the top of the file. |
| `ros_nodes_have_parameter_loader` | Passes when each detected ROS node source file defines the required parameter helper: `declareAndLoadParameter` for C++ nodes or `declare_and_load_parameter` for Python nodes. |
| `ros_cmake_has_required_lint_block` | Passes when every ROS package `CMakeLists.txt` that declares targets with `add_executable(...)` or `add_library(...)` contains the exact required `ament_lint_auto` block, including the configured `.clang-format`, `.clang-tidy`, and `ament_flake8.ini` paths. |
| `ros_packagexml_has_required_testdepends` | Passes when every ROS package `package.xml` contains the exact required `<test_depend>` block for `ament_lint_auto`, `ament_cmake_black`, `ament_cmake_clang_format`, `ament_cmake_clang_tidy`, and `ament_cmake_flake8`. |
| `ros_packagexml_has_required_metadata` | Passes when every ROS package `package.xml` is valid XML and contains non-placeholder `<name>`, non-`0.0.0` `<version>`, `<description>`, at least one non-empty `<license>`, and at least one `<maintainer email="...">...</maintainer>` plus `<author email="...">...</author>` entry that are not left at the default `TODO` placeholder values. |
| `ros_pubsub_topics_private_namespace` | Passes when string-literal topic and service names passed to ROS `create_publisher`, `create_subscription`, `create_service`, and `create_client` calls use the private namespace form `~/...` instead of global or relative names. |
| `demo_launch_remappable_topics_cover_node_pubsub` | Passes when each launch file in `ros2_demo_package/launch/` lists every string-literal pub/sub/service/client name used by the launched node executables in its `remappable_topics` launch arguments. If `ros2_demo_package/launch/` does not exist, the check is skipped as passing. |
| `required_top_level_symlinks` | Passes when the repository root contains symlinks `.devcontainer -> .openads-dev-environment/.devcontainer/`, `.vscode -> .openads-dev-environment/.vscode/`, and `.pre-commit-config.yaml -> .openads-dev-environment/.pre-commit-config.yaml`. |
| `required_root_ci_workflows` | Passes when `.github/workflows/` contains `docker-ros.yml`, `docs.yml`, and `consistency.yml`. |
| `root_ci_workflows_match_templates` | Passes when the root workflow files `.github/workflows/docs.yml` and `.github/workflows/consistency.yml` exactly match the corresponding templates in `.openads-dev-environment/.github/workflow_calls/`. |
| `dev_environment_at_remote_main` | Passes when `.openads-dev-environment` is present as a git repository and its current `HEAD` exactly matches `origin/main`. Update the submodule if it points to any other commit. |
| `readme_generator_is_idempotent` | Passes when running `.openads-dev-environment/scripts/generate_readme.py` produces no README content changes and no additional git status changes. Re-run the generator and commit the result until a second run is clean. |
| `generated_readmes_have_no_todo` | Passes when the repository top-level `README.md` and every generated package `README.md` contain no `TODO` placeholders. Replace all remaining placeholder text before committing. |

### .vscode

This repository stores common [.vscode](https://code.visualstudio.com/docs/getstarted/settings) settings for developing and debugging C++ and Python applications, in particular, ROS applications in container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros).

#### Features

- [*Tasks*](#tasks) ([`tasks.json`](.vscode/tasks.json)) are pre-defined recurring actions (e.g, building a ROS workspace) that can easily be invoked
- [*Debugging Configurations*](#debugging-configurations) ([`launch.json`](.vscode/launch.json)) allow to easily debug applications (e.g., ROS nodes) including breakpoints, stack traces, and more
- *Settings* ([`settings.json`](.vscode/settings.json), [`c_cpp_properties.json`](.vscode/c_cpp_properties.json), [`format/*`](.vscode/format/), [`lint/*`](.vscode/lint/)) store common VS Code settings (e.g., configuring code formatters)
- *Extensions Recommendations* ([`extensions.json`](.vscode/extensions.json)) recommend useful VS Code extensions

#### [Tasks](https://code.visualstudio.com/docs/editor/tasks)

Select *Ctrl+Shift+P / Run Task* to run a task. Tasks are defined in [`tasks.json`](.vscode/tasks.json).

| Name | Description |
| --- | --- |
| Build | Builds ROS workspace using `colcon` (`Ctrl+Shift+B`) |
| Build with Build Type | Builds ROS workspace using `colcon` with given build type |
| Test | Runs tests in ROS workspace using `colcon` |
| Clean | Removes all build artifacts from ROS workspace |
| Clean CMake cache | Builds CMake`s clean target |
| New ROS 2 Package | Creates a new ROS 2 package using [`ros2-pkg-create`](https://github.com/ika-rwth-aachen/ros2-pkg-create) |
| Clone VCS repositories | Clones VCS repositories from `.repos` file using `vcs import` |
| Install dependencies | Install ROS dependencies declared in `package.xml` files using `rosdep` |

#### [Debugging Configurations](https://code.visualstudio.com/docs/editor/debugging)

Select the *Run and Debug* view in the Activity Bar on the side of VS Code (*Ctrl+Shift+D*). Select one of the pre-defined debugging configurations to start debugging. Debugging configurations are defined in [`launch.json`](.vscode/launch.json).

| Name | Description |
| --- | --- |
| ROS 2: Executable | Debug a ROS executable |
| ROS 2: Launch File | Debug ROS nodes started by a launch file |
| Python: ROS 2 Launch file | Debug a ROS 2 Python launch file using the Python debugger |
| Python: Current File | Debug the currently opened Python script |


### devcontainer

This repository stores a common [.devcontainer](https://containers.dev/overview) definition for attaching VS Code to container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros). This allows you to develop and debug ROS applications right from within VS Code.

#### Usage

Select *Ctrl+Shift+P / Dev Containers: Rebuild and Reopen in Container*. VS Code will automatically build and launch a new development container and open your repository inside this container.

By default, the Dev Container image is derived from your repository `origin`:
- GitHub repositories use `ghcr.io/<owner>/<repo>:latest-dev`
- IKA GitLab repositories use `gitlab.ika.rwth-aachen.de:5050/<namespace>/<repo>:latest-dev`

Non-`main` branches append the existing `latest-dev_<branch>_ci` suffix. If the derived image cannot be pulled, the Dev Container helper falls back to building the image locally with `docker-ros`.

#### Customization

Add an `.env` file to the root of your repository to create custom environment variables. The following variables are used within the [`build-local-dockerfile.sh`](.devcontainer/build-local-dockerfile.sh):

```bash
# overwrites the automatically generated base container image name
VSCODE_DEVCONTAINER_IMAGE=""
# forces to build the base container image locally using docker-ros instead of pulling it from a registry
VSCODE_DEVCONTAINER_BUILD_LOCALLY="false"
# chooses a docker-ros git reference if building the base container image locally using docker-ros
VSCODE_DEVCONTAINER_DOCKER_ROS_REF="main"
```
