#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo 'Usage: build-image.sh COMMIT_OR_REF [IMAGE_TAG]' >&2
  exit 1
fi
source_commit=$(git -C "$repo_root" rev-parse --verify "${1}^{commit}")
image_tag=${2:-"em-agent:$source_commit"}
# Archive the selected Git tree: uncommitted files, keys and local data cannot
# enter the build context. Docker also applies the committed .dockerignore.
git -C "$repo_root" archive "$source_commit" |
  docker build --file docker/EM-Agent.Dockerfile \
    --build-arg "SOURCE_COMMIT=$source_commit" \
    --tag "$image_tag" -
# Validate files as the final runtime user before this image can be deployed.
docker run --rm --entrypoint /bin/sh "$image_tag" -c 'test -x /opt/agent-canvas/entrypoint.sh && command -v pdftotext pdftoppm em-env && python -c "import sys; sys.path.insert(0, \"/opt/agent-canvas\"); import science_apps.service, fastapi, uvicorn, yaml"'
docker image inspect "$image_tag" --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
