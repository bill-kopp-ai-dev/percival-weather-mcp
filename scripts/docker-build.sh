#!/bin/sh
# Build the percival-weather-mcp image with reproducible metadata.
#
# The documented build path used to be a bare ``docker build -t ... .``, which
# produced an image whose OCI labels carried ``version=0.0.0`` and
# ``revision=unknown`` (F-014) and whose image ID changed on every build
# (F-007). This script derives both from the checkout:
#
#   * ``VERSION``        — the version declared in ``pyproject.toml``;
#   * ``GIT_SHA``        — the full commit of the checkout;
#   * ``SOURCE_DATE_EPOCH`` — the commit timestamp, so two builds of the same
#     commit produce the same image ID.
#
# The provenance attestation is disabled on purpose: it records the build
# time, which would make the image digest change between two builds of the
# same commit.
#
# Usage:
#   scripts/docker-build.sh [tag] [extra docker build args...]
#
# Examples:
#   scripts/docker-build.sh                          # tag: percival-weather-mcp:dev
#   scripts/docker-build.sh percival-weather-mcp:0.9.0
#   scripts/docker-build.sh percival-weather-mcp:ci --no-cache

set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_ROOT"

TAG=${1:-percival-weather-mcp:dev}
if [ "$#" -gt 0 ]; then
    shift
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker-build: docker is not available on PATH" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "docker-build: git is not available on PATH" >&2
    exit 1
fi

VERSION=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)
if [ -z "$VERSION" ]; then
    echo "docker-build: could not read the version from pyproject.toml" >&2
    exit 1
fi

GIT_SHA=$(git rev-parse HEAD 2>/dev/null || true)
if [ -z "$GIT_SHA" ]; then
    echo "docker-build: not a git checkout; cannot derive the source revision" >&2
    exit 1
fi

SOURCE_DATE_EPOCH=$(git log -1 --format=%ct 2>/dev/null || echo 0)
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    echo "docker-build: warning: the worktree has uncommitted changes;" >&2
    echo "docker-build: the image will not correspond to a released commit." >&2
fi

echo "docker-build: version=${VERSION} revision=${GIT_SHA} source_date_epoch=${SOURCE_DATE_EPOCH}"

# ``rewrite-timestamp=true`` clamps the mtimes written into the layers, and
# ``--provenance=false`` drops the attestation that records the build time;
# without both, two builds of the same commit produce different image IDs.
if docker buildx version >/dev/null 2>&1; then
    exec docker buildx build \
        --provenance=false \
        --output type=docker,rewrite-timestamp=true \
        --build-arg "VERSION=${VERSION}" \
        --build-arg "GIT_SHA=${GIT_SHA}" \
        --build-arg "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" \
        --tag "${TAG}" \
        "$@" \
        .
fi

echo "docker-build: warning: buildx is unavailable; falling back to 'docker build'." >&2
echo "docker-build: warning: the image ID will not be reproducible." >&2
exec docker build \
    --provenance=false \
    --build-arg "VERSION=${VERSION}" \
    --build-arg "GIT_SHA=${GIT_SHA}" \
    --build-arg "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" \
    --tag "${TAG}" \
    "$@" \
    .
