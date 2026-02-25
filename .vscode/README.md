# vscode

This repository stores common [.vscode](https://code.visualstudio.com/docs/getstarted/settings) settings for developing and debugging C++ and Python applications, in particular, ROS applications in container images built by [docker-ros](https://github.com/ika-rwth-aachen/docker-ros). It is recommended to use these settings in conjunction with fb-fi/dev-environment/devcontainer>.


## Features

- [*Tasks*](#tasks) ([`tasks.json`](tasks.json)) are pre-defined recurring actions (e.g, building a ROS workspace) that can easily be invoked
- [*Debugging Configurations*](#debugging-configurations) ([`launch.json`](launch.json)) allow to easily debug applications (e.g., ROS nodes) including breakpoints, stack traces, and more
- *Settings* ([`settings.json`](settings.json), [`c_cpp_properties.json`](c_cpp_properties.json), [`format/*`](format/), [`lint/*`](lint/)) store common VS Code settings (e.g., configuring code formatters)
- *Extensions Recommendations* ([`extensions.json`](extensions.json)) recommend useful VS Code extensions

### [Tasks](https://code.visualstudio.com/docs/editor/tasks)

Select *`Ctrl+Shift+P` / Run Task* to run a task. Tasks are defined in [`tasks.json`](tasks.json).

| Name | Description |
| --- | --- |
| Build | Builds ROS workspace using 'colcon' (`Ctrl+Shift+B`) |
| Build with Build Type | Builds ROS workspace using 'colcon' with given build type |
| Test | Runs tests in ROS workspace using 'colcon' |
| Clean | Removes all build artifacts from ROS workspace |
| Clean CMake cache | Builds CMake's clean target |
| New ROS 2 Package | Creates a new ROS 2 package using 'ros2 pkg create' |
| Clone VCS repositories | Clones VCS repositories from '.repos' file using 'vcs import' |
| Install dependencies | Install ROS dependencies declared in 'package.xml' files using 'rosdep' |

### [Debugging Configurations](https://code.visualstudio.com/docs/editor/debugging)

Select the *Run and Debug* view in the Activity Bar on the side of VS Code (`Ctrl+Shift+D`). Select one of the pre-defined debugging configurations to start debugging. Debugging configurations are defined in [`launch.json`](launch.json).

| Name | Description |
| --- | --- |
| ROS2: Executable | Debug a ROS executable |
| ROS2: Launch File | Debug ROS nodes started by a launch file. Note that this will not work for complex launch files using e.g. lifecycle mechanisms or component loading |
| ROS2: Launch File Debugging | Debug a ROS launch file itself. This config will only run until the generation of the launch config and not launch any nodes. |
| Python: ROS2 Launch file | Debug a ROS2 python launch file using the python debugger. This has the advantage that it works with all python launch files and actually launches the nodes etc., but doesn't debug any started nodes. Also, you might need to source the workspace manually in the Python Debug Console. |
| Python: Current File | Debug the currently opened Python script |


## Installation

### General steps

1. Add this repository as a Git submodule named `.vscode` to the root of any other repository that you would like to use these VS Code settings for.

    ```bash
    git submodule add https://gitlab.ika.rwth-aachen.de/fb-fi/dev-environment/vscode.git .vscode
    ```

1. Make sure that the VS Code extensions recommended in [`extensions.json`](extensions.json) are installed.

### Additional steps for automatic testing of ROS packages in colcon & CI

1. Add formatters and linters to your `package.xml` so that they will be installed by `rosdep` when building `docker-ros` images

    ```xml
      <test_depend>ament_lint_auto</test_depend>

      <!-- add test dependencies on any linter, e.g. -->
      <test_depend>ament_cmake_clang_format</test_depend>
      <test_depend>ament_cmake_clang_tidy</test_depend>
      <test_depend>ament_cmake_flake8</test_depend>
      <test_depend>ament_cmake_mypy</test_depend>
      <test_depend>ament_cmake_pep257</test_depend>
      <test_depend>ament_cmake_xmllint</test_depend>
    ```

    Note that Clang Tidy does not work with ROS foxy, so if you want to write packages working with both foxy and newer versions, conditionally exclude it using

    ```
      <!-- install ament_clang_tidy if not 'foxy' (due to missing clang-tidy-6.0 - see https://github.com/ament/ament_lint/issues/406) -->
      <test_depend condition="$ROS_DISTRO != 'foxy'">ament_cmake_clang_tidy</test_depend>  
    ```

1. Configure tests in `CmakeLists.txt`

    ```cmake
    if(BUILD_TESTING)
      find_package(ament_lint_auto REQUIRED)

      # define ament_lint config files
      set(ament_cmake_clang_format_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/.vscode/format/.clang-format)
      set(ament_cmake_clang_tidy_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/.vscode/lint/.clang-tidy)
      set(ament_cmake_flake8_CONFIG_FILE ${CMAKE_CURRENT_SOURCE_DIR}/.vscode/lint/ament_flake8.ini)

      ament_lint_auto_find_test_dependencies()
    endif()

    ```

1. To check conformity with formatters and linters in your CI pipeline, add the following variables to the `.gitlab-ci.yml`:

    ```yaml
      ENABLE_INDUSTRIAL_CI: 'true'
      TARGET_CMAKE_ARGS : '-DCMAKE_EXPORT_COMPILE_COMMANDS=1' # Only needed if clang-tidy is used
    ```
