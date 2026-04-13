#!/bin/bash

if [[ -f ".env" ]]; then
    source ".env"
fi

trim_git_suffix() {
    local value="$1"
    value="${value%/}"
    value="${value%.git}"
    printf '%s\n' "${value}"
}

slugify_branch_name() {
    local branch_name="$1"
    if [[ -z "${branch_name}" ]]; then
        printf '\n'
        return
    fi
    printf '%s' "${branch_name}" \
        | iconv -t ascii//TRANSLIT \
        | sed -r 's/[^a-zA-Z0-9]+/-/g' \
        | sed -r 's/^-+|-+$//g' \
        | tr 'A-Z' 'a-z'
}

resolve_default_image() {
    local container_registry="ghcr.io"
    local repo_path
    local image_tag="latest-dev"
    local git_remote
    local git_host=""
    local branch_name
    local branch_slug

    repo_path="$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')"

    if git remote | grep -q "^origin$"; then
        git_remote="$(git remote get-url origin)"
        if [[ "${git_remote}" =~ ^git@([^:]+):(.+)$ ]]; then
            git_host="${BASH_REMATCH[1]}"
            repo_path="${BASH_REMATCH[2]}"
        elif [[ "${git_remote}" =~ ^ssh://([^@]+@)?([^/]+)/(.+)$ ]]; then
            git_host="${BASH_REMATCH[2]}"
            repo_path="${BASH_REMATCH[3]}"
        elif [[ "${git_remote}" =~ ^https?://([^/]+)/(.+)$ ]]; then
            git_host="${BASH_REMATCH[1]}"
            repo_path="${BASH_REMATCH[2]}"
        fi

        repo_path="$(trim_git_suffix "${repo_path}")"
        repo_path="$(printf '%s' "${repo_path}" | tr '[:upper:]' '[:lower:]')"

        case "${git_host,,}" in
            gitlab.ika.rwth-aachen.de)
                container_registry="gitlab.ika.rwth-aachen.de:5050"
                ;;
            github.com)
                container_registry="ghcr.io"
                ;;
        esac

        branch_name="$(git branch --show-current)"
        branch_slug="$(slugify_branch_name "${branch_name}")"
        if [[ -n "${branch_slug}" && "${branch_slug}" != "main" ]]; then
            image_tag="latest-dev_${branch_slug}_ci"
        fi
    fi

    printf '%s/%s:%s\n' "${container_registry}" "${repo_path}" "${image_tag}"
}

use_local_build() {
    local value="${1,,}"
    [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

resolve_host_platform() {
    case "$(uname -m)" in
        x86_64|amd64)
            printf 'amd64\n'
            ;;
        aarch64|arm64)
            printf 'arm64\n'
            ;;
        *)
            printf 'Unsupported host architecture for PLATFORM: %s\n' "$(uname -m)" >&2
            return 1
            ;;
    esac
}

generate_docker_ros_env_file() {
    local output_file="$1"
    local workflow_file=".github/workflows/docker-ros.yml"
    local gitlab_ci_file=".gitlab-ci.yml"

    if [[ -f "${workflow_file}" ]]; then
        if awk '
            function escape_env_value(value) {
                gsub(/\\/, "\\\\", value)
                gsub(/"/, "\\\"", value)
                return value
            }

            function normalize_env_value(value, quote) {
                sub(/^[[:space:]]+/, "", value)
                sub(/[[:space:]]+$/, "", value)
                quote = sprintf("%c", 39)
                if (value ~ /^".*"$/ || value ~ ("^" quote ".*" quote "$")) {
                    value = substr(value, 2, length(value) - 2)
                }
                return value
            }

            BEGIN {
                in_with = 0
                with_indent = -1
                entry_count = 0
            }

            {
                line = $0

                if (!in_with) {
                    if (line ~ /^[[:space:]]*with:[[:space:]]*$/) {
                        match(line, /[^[:space:]]/)
                        with_indent = RSTART - 1
                        in_with = 1
                    }
                    next
                }

                if (line ~ /^[[:space:]]*$/) {
                    next
                }

                match(line, /[^[:space:]]/)
                indent = RSTART - 1
                if (indent <= with_indent) {
                    exit
                }
                if (indent != with_indent + 2) {
                    next
                }

                entry = line
                sub(/^[[:space:]]+/, "", entry)
                key = entry
                sub(/:.*/, "", key)
                value = entry
                sub(/^[^:]+:[[:space:]]*/, "", value)

                gsub(/-/, "_", key)
                key = toupper(key)
                if (key == "TARGET" || key == "PLATFORM") {
                    next
                }
                value = normalize_env_value(value)
                value = escape_env_value(value)

                printf "%s=\"%s\"\n", key, value
                entry_count++
            }

            END {
                if (entry_count == 0) {
                    exit 1
                }
            }
        ' "${workflow_file}" > "${output_file}"; then
            return 0
        fi

        echo "Failed to generate docker-ros env file from '${workflow_file}'" >&2
        return 1
    fi

    if [[ -f "${gitlab_ci_file}" ]]; then
        if awk '
            function escape_env_value(value) {
                gsub(/\\/, "\\\\", value)
                gsub(/"/, "\\\"", value)
                return value
            }

            function normalize_env_value(value, quote) {
                sub(/^[[:space:]]+/, "", value)
                sub(/[[:space:]]+$/, "", value)
                quote = sprintf("%c", 39)
                if (value ~ /^".*"$/ || value ~ ("^" quote ".*" quote "$")) {
                    value = substr(value, 2, length(value) - 2)
                }
                return value
            }

            BEGIN {
                in_job = 0
                in_variables = 0
                job_indent = -1
                variables_indent = -1
                entry_count = 0
            }

            {
                line = $0

                if (line ~ /^[[:space:]]*#/) {
                    next
                }

                if (!in_job) {
                    if (line ~ /^docker-ros:[[:space:]]*$/) {
                        in_job = 1
                        job_indent = 0
                    }
                    next
                }

                if (line ~ /^[[:space:]]*$/) {
                    next
                }

                match(line, /[^[:space:]]/)
                indent = RSTART - 1

                if (indent <= job_indent && line !~ /^docker-ros:[[:space:]]*$/) {
                    exit
                }

                if (!in_variables) {
                    if (indent == job_indent + 2 && line ~ /^[[:space:]]*variables:[[:space:]]*$/) {
                        in_variables = 1
                        variables_indent = indent
                    }
                    next
                }

                if (indent <= variables_indent) {
                    exit
                }
                if (indent != variables_indent + 2) {
                    next
                }

                entry = line
                sub(/^[[:space:]]+/, "", entry)
                key = entry
                sub(/:.*/, "", key)
                value = entry
                sub(/^[^:]+:[[:space:]]*/, "", value)

                if (key == "TARGET" || key == "PLATFORM") {
                    next
                }

                value = normalize_env_value(value)
                value = escape_env_value(value)
                printf "%s=\"%s\"\n", key, value
                entry_count++
            }

            END {
                if (entry_count == 0) {
                    exit 1
                }
            }
        ' "${gitlab_ci_file}" > "${output_file}"; then
            return 0
        fi

        echo "Failed to generate docker-ros env file from '${gitlab_ci_file}'" >&2
        return 1
    fi

    echo "Neither '${workflow_file}' nor '${gitlab_ci_file}' is available for docker-ros env generation" >&2
    return 1
}

# helper function to build image locally with docker-ros
build_with_docker_ros() {

    local docker_dir="docker"
    local docker_ros_dir="${docker_dir}/docker-ros"
    local docker_ros_url="https://github.com/ika-rwth-aachen/docker-ros.git"
    local docker_ros_ref="${VSCODE_DEVCONTAINER_DOCKER_ROS_REF:-main}"
    local docker_ros_created=false
    local build_exit_code=0
    local env_file=".env"
    local env_backup=".env.devcontainer.bak"
    local env_had_file=false
    local host_platform

    # clone docker-ros on-demand if not already available
    if [[ ! -d "${docker_ros_dir}" ]]; then
        mkdir -p "${docker_dir}"
        echo "docker-ros not found at '${docker_ros_dir}', cloning '${docker_ros_url}' (ref '${docker_ros_ref}') on-demand"
        if ! git clone --depth 1 "${docker_ros_url}" "${docker_ros_dir}"; then
            echo "Failed to clone docker-ros from '${docker_ros_url}'" >&2
            return 1
        fi
        if ! git -C "${docker_ros_dir}" fetch --depth 1 origin "${docker_ros_ref}" || ! git -C "${docker_ros_dir}" checkout -q FETCH_HEAD; then
            echo "Failed to check out docker-ros ref '${docker_ros_ref}'" >&2
            rm -rf "${docker_ros_dir}"
            return 1
        fi
        docker_ros_created=true
    fi

    # docker-ros reads its build configuration from .env; generate it only for this build invocation.
    if [[ -f "${env_file}" ]]; then
        env_had_file=true
        cp "${env_file}" "${env_backup}"
    fi
    trap 'if [[ "${env_had_file}" == "true" ]]; then mv "${env_backup}" "${env_file}"; else rm -f "${env_file}"; fi' RETURN
    if ! generate_docker_ros_env_file "${env_file}"; then
        return 1
    fi
    if ! host_platform="$(resolve_host_platform)"; then
        return 1
    fi
    printf "PLATFORM=\"%s\"\n" "${host_platform}" >> "${env_file}"
    printf "TARGET=\"dev\"\n" >> "${env_file}"
    printf "\nIMAGE=\"%s\"\n" "${image}" >> "${env_file}"

    "${docker_ros_dir}/scripts/build.sh"
    build_exit_code=$?

    # cleanup on-demand docker-ros clone after build, if it was created by this script
    if [[ "${docker_ros_created}" == "true" ]]; then
        echo "Removing on-demand docker-ros checkout at '${docker_ros_dir}'"
        rm -rf "${docker_ros_dir}"
    fi

    return "${build_exit_code}"
}

if [[ -z "${VSCODE_DEVCONTAINER_IMAGE:-}" ]]; then
    image="$(resolve_default_image)"
else
    # overwrite image name from .env, if existent
    image="${VSCODE_DEVCONTAINER_IMAGE}"
fi
echo "Dev Container Image: '${image}'"

# build locally if explicitly requested, or when image is unavailable locally/remotely
should_build_locally=false
if use_local_build "${VSCODE_DEVCONTAINER_BUILD_LOCALLY:-}"; then
    should_build_locally=true
else
    if docker pull "${image}" >/dev/null 2>&1; then
        echo "Dev Container Image '${image}' pulled successfully"
    elif docker image inspect "${image}" >/dev/null 2>&1; then
        echo "Dev Container Image '${image}' not pullable, using local image"
    else
        should_build_locally=true
    fi
fi

if [[ "${should_build_locally}" == "true" ]]; then
    if use_local_build "${VSCODE_DEVCONTAINER_BUILD_LOCALLY:-}"; then
        echo "VSCODE_DEVCONTAINER_BUILD_LOCALLY is set, building Dev Container image locally with docker-ros"
    else
        echo "Dev Container Image '${image}' not found locally or remotely, building locally with docker-ros"
    fi
    if ! build_with_docker_ros; then
        echo "Failed to build Dev Container image locally with docker-ros" >&2
        exit 1
    fi
fi

# create local Dockerfile copy with default build arguments to set image/uid/gid
cp ".devcontainer/Dockerfile" ".devcontainer/Dockerfile.local"
sed -i "s~ARG IMAGE~ARG IMAGE=${image}~g" .devcontainer/Dockerfile.local
sed -i "s~ARG DOCKER_UID~ARG DOCKER_UID=$(id -u)~g" .devcontainer/Dockerfile.local
sed -i "s~ARG DOCKER_GID~ARG DOCKER_GID=$(id -g)~g" .devcontainer/Dockerfile.local

# ensure optional local mounts exist
mkdir -p "${HOME}/.claude"
mkdir -p "${HOME}/.codex"
