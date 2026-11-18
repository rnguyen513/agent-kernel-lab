# Recovery and storage

Use `sudo python3 akl.py checkpoint create LABEL` with both guests completely off. A checkpoint combines internal qcow2 snapshots with NVRAM, TPM state and domain XML. `backup create LABEL` instead copies standalone qcow2 disks and firmware/TPM state. Both refuse overwrite, hash bundle contents, flush storage and write `COMPLETE` only at the end.

```sh
sudo python3 akl.py checkpoint validate LABEL
sudo python3 akl.py checkpoint restore LABEL
# Or use 'backup validate/restore' for a full backup.
```

Restore validates the entire pair and creates a unique rollback bundle before applying changes. A checkpoint rollback is another checkpoint; a full-image restore first creates a full backup because replacing a disk removes its internal snapshot history. Restore leaves both VMs off and the network isolated. Full backups can be slow and require enough free space for both rollback images and temporary replacement images.

Recovery is tied to this instance's exact UUIDs, disk paths, firmware paths and configuration. It is not a cross-host migration/import tool. Back up the private host workspace separately if you need disaster recovery: it contains configuration, SSH keys and ownership manifests. Do not publish it. Same-volume backups do not protect against physical drive failure.

A restore is a multi-step operation, not an atomic transaction across two VMs. An interruption leaves `state/restore-in-progress.json`; normal startup refuses to proceed. Keep the guests off, inspect the recorded rollback and completed steps, and perform a supervised repair. Do not delete the journal just to make `start` succeed. Incomplete bundles lack `COMPLETE` and are never treated as valid recovery points. After full image replacement, older internal checkpoint bundles may no longer match the active disks; validation will reject them.

The watchdog observes new kernel storage/controller errors and the configured mount. On a fault it verifies instance UUIDs and pauses running lab guests. It never resumes automatically. Diagnose the physical mount/controller/filesystem before resuming; don't reset NVRAM, discard TPM state or force-reboot to solve a host disk problem. A tool sandbox can expose a read-only mount view even when the actual host is writable: verify through a scoped host inspection before declaring a fault.

Avoid active-disk qemu-img operations, moving firmware independently of disks, speculative deletion of Docker/user data, or treating an internal checkpoint as a second physical copy. Store exported evidence and a separate full backup on another device when needed.
