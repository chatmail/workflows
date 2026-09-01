#!/usr/bin/env bash
# Pack/unpack a cmsend account as a small sqlite-dump + accounts.toml so it fits a 64KiB
# GitHub secret, which the naive compressed .config/cmsend directory does not.

set -euo pipefail
case "${1:-}" in
  pack)   # pack <cmsend-dir> -> base64 seed on stdout
    cfg=${2:?cmsend dir}; w=$(mktemp -d)
    cp "$cfg/accounts.toml" "$w/"
    for db in "$cfg"/*/dc.db; do
      a=$(basename "$(dirname "$db")"); mkdir -p "$w/$a"
      sqlite3 "$db" ".dump" > "$w/$a/dc.sql"
    done
    tar -C "$w" -czf - . | base64 -w0; rm -rf "$w" ;;

  unpack) # unpack <cmsend-dir>  (base64 seed on stdin)
    cfg=${2:?cmsend dir}; mkdir -p "$cfg"
    base64 -d | tar -C "$cfg" -xzf -
    for s in "$cfg"/*/dc.sql; do
      d=$(dirname "$s"); sqlite3 "$d/dc.db" < "$s"; mkdir -p "$d/dc.db-blobs"; rm -f "$s"
    done ;;

  *) echo "usage: $0 pack|unpack <cmsend-dir>" >&2; exit 2 ;;
esac
