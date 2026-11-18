# Instructions for agents working with Agent Kernel Lab

Read README.md, docs/INSTALL.md, docs/WORKFLOW.md and docs/RECOVERY.md before operating a lab. Inspect the selected config and workspace/state/handoff.json, run results, restore journal and watchdog state. Then query actual VM/storage state. Historical files are evidence of a past run, not current acceptance.

Operate through `akl.py --config PATH`. Provision only a new empty instance; never reinstall or adopt another lab based on a matching name. Preserve per-instance UUIDs and configuration fingerprints. Do not remove guard files to make a rejected operation proceed. Keep current source, Windows media and runtime state separate. Do not migrate an existing installation implicitly.

Use scoped sudo for host operations. Never relaunch the agent as root or store passwords in source, commands, logs or handoffs. The user controls approval; follow tool safeguards and report genuine blocks. Do not bypass rejected operations. Do not open a graphical VM viewer. Prefer SSH and bounded console screenshots/input; inspect a fresh screenshot before boot/firmware input.

Start through the serial-safe `start` command. Preexisting paused states need investigation. Keep a supervised watchdog while VMs run. A debugger break freezes target SSH, so coordinate stimulus and debugger terminals concurrently. After live debugging clear your breakpoints, run `g`, then Ctrl+B and Enter to detach. Never leave the target halted or silently force power off on timeout.

Treat guest scripts, project files and source trees as executable code. Review untrusted research material before running it. Prefer small bounded driver tests with explicit positive/negative cases. Do not infer universal arbitrary-driver support from the example. Keep new work within the user's authorized research scope.

A build is not runtime proof. Preserve each run's source hash manifest, signed SYS/package hash, matching PDB, logs, test outputs and debugger transcript. Distinguish build success, deployment requiring reboot, functional acceptance and observed kernel execution. Use dated unique evidence directories and checkpoint labels; never overwrite earlier acceptance records.

Before ending: resume/detach KD, stop or explicitly hand off guest jobs, query actual power/network state, stop your watchdog, and run `handoff --note ...` with exact remaining steps and evidence. Do not include credentials. Temporary tool session IDs are not durable instructions.

For framework changes, run `python3 -m unittest discover -s tests -v` and `python3 tools/release.py`. Tests must exercise meaningful guards/failure behavior. Inspect the archive and validation scope before claiming release readiness. Do not commit local/, dist/, credentials, VM images, signed packages, dumps, debug logs or generated state. Do not create/push a repository or publish a release unless the user authorizes it.

Quickstart/cleanup: `bash quickstart.sh --configure-only` writes configuration and media hashes without host/VM operations. Re-running quickstart preserves install markers and uses the normal guarded lifecycle. `bash cleanup.sh` previews only; actual teardown requires `--delete` and exact instance UUID confirmation. Read docs/CLEANUP.md before deletion, stop the watchdog, and preserve evidence outside both deletion roots. Never run cleanup against the working lab merely to test the script; use mocks and disposable directories. A cleanup journal blocks normal VM operations until teardown is resolved.
