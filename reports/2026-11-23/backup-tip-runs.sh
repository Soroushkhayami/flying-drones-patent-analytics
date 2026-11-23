#!/usr/bin/env bash
# Run from the TIP project checkout. The two active run folders are read-only inputs.
set -euo pipefail

checkout=$(git rev-parse --show-toplevel)
runs="$checkout/outputs/runs"
run_dirs=(TEST/phase2a-test-001 PROD/phase2a-prod-001)
for run in "${run_dirs[@]}"; do
    if [[ ! -f "$runs/$run/manifest.json" ]]; then
        echo "Cannot find $runs/$run/manifest.json. Run this in the TIP project checkout." >&2
        exit 1
    fi
done

backup=$(mktemp -d "$(dirname "$checkout")/phase2a-backup.XXXXXXXX")
echo "Backup directory: $backup"
for run in "${run_dirs[@]}"; do
    name=${run##*/}
    prefix="$backup/$name.tar.gz"
    echo "Packing $run ..."
    # Each piece fits below GitHub's 2 GiB per-release-asset limit.
    tar -C "$runs" -czf - "$run" | split -b 1024M -d -a 4 - "$prefix.part-"
    parts=("$prefix".part-*)
    echo "Checking archive against the files on TIP ..."
    cat "${parts[@]}" | tar --compare --gzip --directory="$runs" --file=-
    if (( ${#parts[@]} == 1 )); then
        mv -- "${parts[0]}" "$prefix"
    fi
done

(
    cd "$backup"
    sha256sum phase2a-*.tar.gz* > SHA256SUMS.txt
    sha256sum --check SHA256SUMS.txt
)
echo "Backup verified. Download every file in: $backup"
