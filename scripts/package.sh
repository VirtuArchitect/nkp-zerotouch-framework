#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:-$(tr -d '[:space:]' < "$repo_root/VERSION")}"
dist="$repo_root/dist"
staging="$dist/nkp-zerotouch-framework-$version"
archive="$dist/nkp-zerotouch-framework-$version.tar.gz"

rm -rf "$staging"
mkdir -p "$staging"
cp -a "$repo_root"/configs "$repo_root"/dashboard "$repo_root"/docs "$repo_root"/scripts "$repo_root"/templates "$repo_root"/tests "$repo_root"/tools "$staging"/
cp "$repo_root"/README.md "$repo_root"/LICENSE "$repo_root"/VERSION "$repo_root"/CHANGELOG.md "$repo_root"/SECURITY.md "$repo_root"/CONTRIBUTING.md "$repo_root"/Dockerfile "$repo_root"/Containerfile "$repo_root"/.gitignore "$staging"/
tar -czf "$archive" -C "$dist" "nkp-zerotouch-framework-$version"
echo "Package created: $archive"
