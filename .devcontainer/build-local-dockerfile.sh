#!/bin/bash

# TODO: adjust to GHCR or DockerHub or whereever images are going to be stored

# try to get default image name from git remote
container_registry="gitlab.ika.rwth-aachen.de:5050"
if git remote | grep -q "^origin$"; then
  git_remote=$(git remote get-url origin)
  if [[ "$git_remote" == git@* ]]; then
    repo_path=$(git remote get-url origin | cut -d':' -f2 | rev | cut -d'.' -f2- | rev | tr '[:upper:]' '[:lower:]')
  else
    repo_path=$(git remote get-url origin | sed -e 's/https:\/\/[^/]*\///' -e 's/\.git\/\?$//' | tr '[:upper:]' '[:lower:]')
  fi
  image_tag="latest-dev"
  git_branch_slug=$(git branch --show-current | iconv -t ascii//TRANSLIT | sed -r s/[^a-zA-Z0-9]+/-/g | sed -r s/^-+\|-+$//g | tr A-Z a-z)
  if [[ "$git_branch_slug" != "main" ]]; then
    image_tag="latest-dev_${git_branch_slug}_ci"
  fi
fi
image="${container_registry}/${repo_path}:${image_tag}"
fallback_image="${container_registry}/${repo_path}:latest-dev"
second_fallback_image="rwthika/ros2:latest"

# overwrite image name from .envrc, if existent
if [[ -f .envrc ]]; then
  source .envrc
fi
image=${VSCODE_DEVCONTAINER_IMAGE:-$image}

# check if image exists locally or can be pulled, else use fallback images
if ! docker image inspect "$image" &>/dev/null && ! docker pull "$image" &>/dev/null; then
  image="$fallback_image"
  if ! docker image inspect "$image" &>/dev/null && ! docker pull "$image" &>/dev/null; then
    image="$second_fallback_image"
  fi
fi

# determine UID/GID
uid=$(id -u)
gid=$(id -g)

# create local Dockerfile copy with default build arguments
cp .devcontainer/Dockerfile .devcontainer/Dockerfile.local
sed -i "s~ARG IMAGE~ARG IMAGE=${image}~g" .devcontainer/Dockerfile.local
sed -i "s~ARG DOCKER_UID~ARG DOCKER_UID=${uid}~g" .devcontainer/Dockerfile.local
sed -i "s~ARG DOCKER_GID~ARG DOCKER_GID=${gid}~g" .devcontainer/Dockerfile.local

# ensure optional local mounts exist to avoid devcontainer startup failures
mkdir -p "${HOME}/.codex"
