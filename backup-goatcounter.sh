#!/bin/bash
# Back up the GoatCounter database without the session store.
#
# GoatCounter writes its in-memory session table (literal User-Agent + IP, see
# README "Session caveat") to the `store` table on shutdown. A plain copy of
# the volume would carry those full IPs into backups, which the privacy
# policies don't cover — so the snapshot is taken with VACUUM INTO, `store` is
# emptied in the copy, and the copy is vacuumed again so the deleted rows
# don't survive in free pages.
#
# Usage: ./backup-goatcounter.sh [backup-dir]   (default: ./backups)
# Backups older than KEEP_DAYS (default 30) are deleted afterwards, so stats
# never outlive the 12-month retention promised in the policies via backups.
set -euo pipefail

cd "$(dirname "$0")"
dir="${1:-backups}"
keep_days="${KEEP_DAYS:-30}"
tmp=/tmp/backup.sqlite3
out="$dir/goatcounter-$(date +%F).sqlite3.gz"

mkdir -p "$dir"
docker compose exec -T goatcounter sh -c "
  rm -f $tmp &&
  goatcounter db query \"VACUUM INTO '$tmp'\" &&
  goatcounter db query -db sqlite3+$tmp 'DELETE FROM store' &&
  goatcounter db query -db sqlite3+$tmp 'VACUUM'" >/dev/null
docker compose exec -T goatcounter cat "$tmp" | gzip > "$out"
docker compose exec -T goatcounter rm -f "$tmp"

find "$dir" -name 'goatcounter-*.sqlite3.gz' -mtime +"$keep_days" -delete
echo "Wrote $out"
