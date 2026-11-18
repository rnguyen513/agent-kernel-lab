# Remove an instance

Cleanup permanently removes one selected, recorded Agent Kernel Lab instance. It is not a host-wide uninstall or an importer for unrelated/legacy VMs.

Preview first:

```sh
bash cleanup.sh
# Or select another instance:
bash cleanup.sh --config /absolute/path/to/lab.json
```

The default is **preview only**. The script requests scoped sudo to inspect system libvirt and firmware state, then lists the exact VM identities, network, directories and external state it proposes to remove. Stop the watchdog terminal and detach/resume KD before teardown. Shut down the guests normally:

```sh
sudo python3 akl.py --config local/lab.json stop
bash cleanup.sh --config local/lab.json --delete
```

Deletion requires typing the complete instance UUID printed by the preview. For deliberate automation, use both `--delete` and `--confirm INSTANCE_UUID`. Active guests block deletion unless `--force` is supplied as well; that option powers them off immediately and discards running state. Use it only when that loss is intended.

## What is removed

- The selected dev/target domain definitions and their managed-save/snapshot/checkpoint metadata.
- The instance's libvirt network.
- Its NVRAM, TPM state, private debug socket and standard per-domain log files.
- The **entire configured storage directory**, including disks, checkpoints, full backups, staged Windows/EWDK media and credential-bearing seed ISOs.
- The **entire configured workspace**, including SSH keys, recovery credentials, evidence, source/build archives, screenshots, logs and runtime journals.
- The selected configuration file.

Save any evidence or backups you need outside those directories first. Shared host packages/services, the repository checkout, the mounted volume itself, and original downloads outside the instance's directories are retained. The preview identifies retained download paths. Cleanup does not format/unmount disks or prune unrelated Docker/user data.

## Ownership and interruption checks

Cleanup validates the recorded configuration fingerprint, instance UUIDs, storage ownership marker and filesystem UUID. Other domains referencing this network, bridge, disks, media, firmware or debug socket block the entire operation. Nested mounts, unexpected firmware paths, identity mismatches and an active watchdog also block deletion. It never uses libvirt's broad `--remove-all-storage` option.

A config-only instance created by current `init` or quickstart can be removed through its private workspace marker without provisioning first. An older unprovisioned workspace with no ownership marker requires manual inspection; cleanup will not invent ownership.

Deletion is not atomic. If it fails after starting, the remaining workspace contains `state/cleanup-in-progress.json`; normal VM startup refuses that instance. Resolve the reported issue and rerun cleanup with the same config and UUID. Already undefined guests are handled using the recorded identities. If interruption occurs during the final removal of the config/workspace, inspect the printed local paths for leftovers; do not recreate VMs to make cleanup run.

No tool can guarantee erasure of data retained in filesystem snapshots, physical backups or external logging systems. This script removes the instance's owned files and definitions; it is not a secure disk-erasure utility.
