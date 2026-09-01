#!/bin/bash
#
# Install or refresh the shared chatmail/workflows in the repository in
# the current working directory, and stage them in your repo:
#
#     ../workflows/scripts/set-workflows.sh
#

set -euo pipefail

shared=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repo=$(git rev-parse --show-toplevel)
cd "$repo"

if [ "$repo" = "$shared" ]; then
    echo "set-workflows.sh installs into other repositories, not this one" >&2
    exit 1
fi

if [ ! -f pyproject.toml ]; then
    echo "no pyproject.toml: py-checks does not apply here" >&2
    exit 1
fi

remote=$(git remote get-url origin 2>/dev/null || echo "")
slug=$(printf '%s\n' "${remote%.git}" | sed -n 's#.*github\.com[:/]##p')

if [ -z "$slug" ]; then
    echo "origin is not a github.com repository: ${remote:-none}" >&2
    echo "cliff.toml needs owner/name for the links in its changelog" >&2
    exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

install() {
    local src=$1 dst=$2 state=created
    if [ -f "$dst" ]; then
        if cmp -s "$src" "$dst"; then state=unchanged; else state=updated; fi
    fi
    mkdir -p "$(dirname "$dst")"
    cp -- "$src" "$dst"
    git add -- "$dst"
    printf '  %-9s %s\n' "$state" "$dst"
}

install_once() {
    local src=$1 dst=$2
    if [ -f "$dst" ]; then
        printf '  %-9s %s\n' "kept" "$dst"
        return
    fi
    install "$src" "$dst"
}

echo "$slug:"

install "$shared/templates/ci.yml" .github/workflows/ci.yml
install_once "$shared/templates/release.yml" .github/workflows/release.yml

# The first line tells a human to do by hand what the script does.
sed -e "/^# Copy to /d" -e "s|github.com/OWNER/REPO|github.com/$slug|g" \
    "$shared/templates/cliff.toml" >"$tmp/cliff.toml"
install_once "$tmp/cliff.toml" cliff.toml

echo
echo "review with: git status && git diff --cached"
