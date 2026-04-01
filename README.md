# openads-dev-environment

<p align="center">
  <a href="https://github.com/openads-project"><img src="https://img.shields.io/badge/OpenADS-f5ff01"/></a>
  <a href="https://www.ros.org"><img src="https://img.shields.io/badge/ROS 2-jazzy-22314e"/></a>
  <a href="https://github.com/openads-project/openads_ros2_demo_repository/blob/main/LICENSE"><img src="https://img.shields.io/github/license/openads-project/openads_ros2_demo_repository"/></a>
</p>

This repository defines a common development environment for and enforces consistency of components of [***OpenADS***](https://github.com/openads-project), the *Open Automated Driving Stack*.

**Features**
- [.vscode](#vs-code-configuration) settings, recommended extensions, tasks, and debugging configurations
- [.devcontainer](#dev-container) definition for developing and debugging in container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros)
- [pre-commit hooks](#pre-commit-hooks) configuration for running linting and formatting on each commit
- [README generator](#readme-generator) for generating common-style repository READMEs
- [consistency checker](#consistency-checker) for enforcing conventions across repositories
- [CI workflow templates](#ci-workflows) for building and testing container images, building documentation, and checking repository consistency


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
3. Copy the CI workflow templates into your repository.
    ```bash
    # GitHub
    mkdir -p .github/workflows
    cp .openads-dev-environment/.github/workflow_calls/*.yml .github/workflows/

    # GitLab
    cp .openads-dev-environment/.gitlab-ci.template.yml .gitlab-ci.yml
    ```
4. Customize the copied CI workflows to fit your repository, in particular `base-image` and `command` of the `docker-ros` job.
5. Install the recommended VS Code extensions.  
    > *Ctrl+Shift+P / Extensions: Show Recommended Extensions / Install Workspace Recommended Extensions (Cloud Download Icon)*
6. *(optional)* Install Git pre-commit hooks.
    ```bash
    pip install pre-commit
    pre-commit install
    ```


## Details

### VS Code Configuration

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
| Build | Builds ROS target workspace using `colcon` (`Ctrl+Shift+B`) |
| Build with Build Type | Builds ROS target workspace using `colcon` with given build type |
| Test | Runs tests in ROS target workspace using `colcon` |
| Clean | Removes all build artifacts from ROS workspace |
| Clean CMake cache | Builds CMake's clean target |
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

### Dev Container

This repository stores a common [.devcontainer](https://containers.dev/overview) definition for attaching VS Code to container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros). This allows you to develop and debug ROS applications right from within VS Code.

#### Usage

Select *Ctrl+Shift+P / Dev Containers: Rebuild and Reopen in Container*. VS Code will automatically build and launch a new development container and open your repository inside this container.

By default, the Dev Container image is derived from your repository `origin`, e.g., `ghcr.io/<owner>/<repo>:latest-dev` or `latest-dev_<branch>_ci` on non-default branches. If the derived image cannot be pulled, the Dev Container helper falls back to building the image locally with [docker-ros](https://github.com/ika-rwth-aachen/docker-ros#build-images-locally).

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

### Pre-Commit Hooks

This repository stores a common [pre-commit](https://pre-commit.com/) configuration for running linting and formatting checks before committing code.

#### Installation

Pre-commit hooks are auto-installed in the [Dev Container](#dev-container). On the host, the `pre-commit` package is required.

```bash
pip install pre-commit
pre-commit install
```

#### Usage

Pre-commit hooks will automatically run on `git commit` and check all staged files. If any check fails, the commit is aborted and you can fix the issues before re-committing.

Pre-commit hooks can also be run manually.

```bash
pre-commit run --all-files
```

### README Generator

Use [`generate_readme.py`](scripts/generate_readme.py) to generate common-style top-level and package-level READMEs. These READMEs are expected to be auto-generated by the [consistency checker](#consistency-checker), but expect some customization and allow some freedom.

```bash
.openads-dev-environment/scripts/generate_readme.py
```

### Consistency Checker

Use [`check_repository_consistency.py`](scripts/check_repository_consistency.py) to run a set of checks that enforce consistency and conventions across repositories. This is set up to be run in CI, but can also be run locally to check for issues before pushing.

```bash
.openads-dev-environment/scripts/check_repository_consistency.py
```

#### List of Consistency Checks

| Name | Description |
| --- | --- |
| `cpp_code_has_doxygen_docs` | Passes when every tracked C++ function that Doxygen discovers has documentation on at least one emitted declaration or definition record. |
| `default_launch_remappable_topics_cover_node_pubsub` | Passes when each default ROS package launch file lists every string-literal pub/sub/service/client name used by the launched node executables in its `remappable_topics` launch arguments. Packages without a default launch file are skipped. |
| `dev_environment_at_remote_main` | Passes when `.openads-dev-environment` is present as a git repository and its current `HEAD` exactly matches `origin/main`. Update the submodule if it points to any other commit. |
| `generated_readmes_have_no_todo` | Passes when the repository top-level `README.md` and every generated package `README.md` contain no `TODO` placeholders. Replace all remaining placeholder text before committing. |
| `no_top_level_package_xml` | Passes when the repository root does not contain a `package.xml`. ROS packages must live in subdirectories instead of treating the whole repository as one package. |
| `repository_name_not_ending_with_er` | Passes when the repository directory name does not end with `er`, enforcing names such as `trajectory_optimization` instead of `trajectory_optimizer`. |
| `readme_generator_is_idempotent` | Passes when running `.openads-dev-environment/scripts/generate_readme.py` produces no README content changes and no additional git status changes. Re-run the generator and commit the result until a second run is clean. |
| `required_root_ci_workflows` | Passes when `.github/workflows/` contains `docker-ros.yml`, `docs.yml`, and `consistency.yml`. |
| `required_top_level_symlinks` | Passes when the repository root contains symlinks `.devcontainer -> .openads-dev-environment/.devcontainer/`, `.vscode -> .openads-dev-environment/.vscode/`, and `.pre-commit-config.yaml -> .openads-dev-environment/.pre-commit-config.yaml`. |
| `root_ci_workflows_match_templates` | Passes when the root workflow files `.github/workflows/docs.yml` and `.github/workflows/consistency.yml` exactly match the corresponding templates in `.openads-dev-environment/.github/workflow_calls/`. |
| `ros_cmake_has_required_lint_block` | Passes when every ROS package `CMakeLists.txt` that declares targets with `add_executable(...)` or `add_library(...)` contains the exact required `ament_lint_auto` block, including the configured `.clang-format`, `.clang-tidy`, and `ament_flake8.ini` paths. |
| `ros_nodes_have_parameter_loader` | Passes when each detected ROS node source file defines the required parameter helper: `declareAndLoadParameter` for C++ nodes or `declare_and_load_parameter` for Python nodes. |
| `ros_packagexml_has_required_metadata` | Passes when every ROS package `package.xml` is valid XML and contains non-placeholder `<name>`, non-`0.0.0` `<version>`, `<description>`, at least one non-empty `<license>`, and at least one `<maintainer email="...">...</maintainer>` plus `<author email="...">...</author>` entry that are not left at the default `TODO` placeholder values. |
| `ros_packagexml_has_required_testdepends` | Passes when every ROS package `package.xml` contains the exact required `<test_depend>` block for `ament_lint_auto`, `ament_cmake_black`, `ament_cmake_clang_format`, `ament_cmake_clang_tidy`, and `ament_cmake_flake8`. |
| `ros_pubsub_topics_private_namespace` | Passes when string-literal topic and service names passed to ROS `create_publisher`, `create_subscription`, `create_service`, and `create_client` calls use the private namespace form `~/...` instead of global or relative names. |
| `source_files_have_copyright_notice` | Passes when every tracked `.cpp`, `.hpp`, and `.py` file contains the required copyright notice and `SPDX-License-Identifier: Apache-2.0` near the top of the file. |
| `top_level_license_apache2` | Passes when a top-level `LICENSE` file exists and contains the Apache 2.0 license text markers (`Apache License`, `Version 2.0, January 2004`, `http://www.apache.org/licenses/`). |

### CI Workflows

This repository stores CI workflow templates for the following use cases. CI workflows are defined for [GitHub Actions](https://github.com/features/actions) in [`.github/workflow_calls`](.github/workflow_calls) and for [GitLab CI/CD](https://docs.gitlab.com/ci/) in [`.gitlab-ci.template.yml`](.gitlab-ci.template.yml).

| Name | Description |
| --- | --- |
| `consistency` | Runs the [consistency checker](#consistency-checker) to check for repository consistency and convention adherence. |
| `docker-ros` | Uses [docker-ros](https://github.com/ika-rwth-aachen/docker-ros) to build, test, and push a container image containing the ROS packages of the repository. |
| `docs` | Builds and deploys documentation using [GitHub Pages](https://docs.github.com/en/pages) or [GitLab Pages](https://docs.gitlab.com/ee/user/project/pages/). |
