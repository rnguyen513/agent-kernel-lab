#!/usr/bin/env bash
set -euo pipefail
akl_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$akl_script_dir/tools/quickstart.py" "$@"
