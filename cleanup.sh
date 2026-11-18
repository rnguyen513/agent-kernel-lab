#!/usr/bin/env bash
set -euo pipefail
akl_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The Python entry point elevates only after parsing options; --help needs no sudo.
exec /usr/bin/python3 "$akl_script_dir/tools/cleanup.py" "$@"
