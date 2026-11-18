# Changelog

## Unreleased

- Added `quickstart.sh` for interactive configuration, media hashing, host checks and resumable Windows installation.
- Added preview-first `cleanup.sh` with explicit UUID confirmation, ownership/shared-resource checks, optional forced stop and complete instance removal.
- Added watchdog lifetime locking so cleanup cannot race an active storage monitor.

## 0.1.0 — research preview

- Extracted a portable Linux/KVM framework from a working two-VM Windows kernel lab.
- Added validated per-instance configuration, JSON CLI, offline unattended installation and headless access.
- Preserved serial-safe boot ordering, bounded console control, storage monitoring and cold paired recovery.
- Included the observed KMDF IOCTL example, reproducible source capture and explicit debugger acceptance workflow.
- Added host tests, source-only deterministic packaging, licensing, CI and agent handoff instructions.
- Fresh-install acceptance of the portable release remains unverified; see docs/VALIDATION.md.
