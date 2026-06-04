#!/usr/bin/env bash
set -euo pipefail

version="${1:-dev}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dist="$repo_root/dist"
staging="$dist/nkp-zerotouch-framework-$version"
archive="$dist/nkp-zerotouch-framework-$version.tar.gz"

rm -rf "$staging"
mkdir -p "$staging"
cp -a "$repo_root"/configs "$repo_root"/docs "$repo_root"/scripts "$repo_root"/templates "$repo_root"/tests "$repo_root"/tools "$staging"/
cp "$repo_root"/README.md "$repo_root"/LICENSE "$repo_root"/.gitignore "$staging"/
tar -czf "$archive" -C "$dist" "nkp-zerotouch-framework-$version"
echo "Package created: $archive"
