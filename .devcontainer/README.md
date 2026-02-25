# devcontainer

This repository stores a common [devcontainer](https://containers.dev/overview) definition for attaching VS Code to [docker-ros](https://github.com/ika-rwth-aachen/docker-ros) container images. This allows you to develop and debug ROS applications right from within VS Code. It is recommended to use the container development in conjunction with fb-fi/dev-environment/vscode>.

## Installation

Add this repository as a Git submodule named `.devcontainer` to the root of any other repository that you would like to use VS Code with inside a container.

```bash
git submodule add https://gitlab.ika.rwth-aachen.de/fb-fi/dev-environment/devcontainer.git .devcontainer
```

Also make sure that the VS Code extension pack [Remote Development](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) is installed.

## Usage

Open the root of your repository (where the `.devcontainer` submodule is placed) in VS Code and run the VS Code command *Dev Containers: Rebuild and Reopen in Container* (`Ctrl+Shift+P`). VS Code will automatically build and launch a new development container and open your repository inside this container.

To leave the Dev Container and go back to your local folder run the VS Code command *Dev Containers: Reopen Folder Locally* (`Ctrl+Shift+P`)

## Customization

Add an `.envrc` file to the root of your repository to create custom environment variables. The following variables are used within the `build-local-dockerfile.sh`:

```bash
export VSCODE_DEVCONTAINER_IMAGE=<your-custom-docker-image> # overwrites the automatically generated docker image path
```