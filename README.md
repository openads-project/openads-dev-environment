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
3. Copy the template GitHub CI workflow definitions.
    ```bash
    mkdir -p .github/workflows
    cp .openads-dev-environment/.github/workflow_calls/*.yml .github/workflows/
    ```
4. Install the recommended VS Code extensions.  
    > *Ctrl+Shift+P / Extensions: Show Recommended Extensions / Install Workspace Recommended Extensions (Cloud Download Icon)*

## Usage

1. Reopen the repository in a [Dev Container](https://code.visualstudio.com/docs/devcontainers/containers).
    > *Ctrl+Shift+P / Dev Containers: Rebuild and Reopen in Container*
1. Develop and debug your application in a defined development environment with pre-defined settings and configurations, see [.vscode Features](#features).


## Details

This repository contains common development environment configuration, including:
- [.vscode](#vscode) settings, recommended extensions, tasks, and debugging configurations
- [.devcontainer](#devcontainer) definition for developing and debugging in container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros)
- [GitHub CI workflow templates](.github/workflows/), including documentation generation and consistency checks
- [pre-commit](.pre-commit-config.yaml) configuration for running linting and formatting

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
