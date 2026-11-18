# Validation scope — 2026-11-18

## Portable framework validation

The release is a **research preview**, ready for source review and a dedicated fresh-install acceptance run. It is not yet certified as a fully unattended installer across Linux distributions or Windows releases.

Completed on the reference Ubuntu 22.04 host:

- Python unit/failure-path tests for configuration, instance and filesystem identity, unattended XML escaping, guest-template rendering, SSH argument handling, transfer path restrictions, bounded console input, lifecycle ordering and interrupted recovery.
- Recovery tests confirming a corrupt second guest prevents rollback creation or image mutation, including when a bundle's hash manifest was recomputed after editing.
- Real QEMU integration: create an 8 MiB qcow2, write pattern A, checkpoint, overwrite with pattern B, restore, verify pattern A and check image structure.
- `virt-install --print-xml 1 --dry-run` against libvirt 8.0, followed by `virt-xml-validate` for generated dev/target domains and isolated/NAT networks. No VM definition or startup was performed for these checks.
- Parsing all 19 rendered guest PowerShell helpers with official PowerShell 7.4.6 on Linux, whose archive was checked against the published SHA256. This checks syntax, not Windows cmdlet/runtime behavior. CI additionally parses helpers with Windows PowerShell 5.1; the [repository Actions page](https://github.com/rnguyen513/agent-kernel-lab/actions) records results for published commits.
- Portable template-renderer regression coverage that blocks Linux-only modules to reproduce the Windows import boundary.
- Deterministic source ZIP and release archive checks; rejection of symlinks, unexpected artifacts, private-key text and token-bearing download URLs in publication inputs. UTF-16 upstream INF templates are preserved byte-for-byte.

The exact test count and archive digest are recorded in `docs/validation-results.json` and the release SHA256 sidecar. No fresh Windows installation or full VM restore was executed through the new portable package during this packaging task. The existing lab was left powered off. The new code does not import or take ownership of it.

## Quickstart and cleanup additions

The host suite also covers configuration-only setup with no host commands, existing-config preservation, setup resumption, entry points launched outside the checkout, and blocked teardown for wrong identities, shared storage/bridges, active guests/watchdogs and nested mounts. Deletion tests use fake libvirt responses and disposable directories, including a symlink whose external target must survive. Cleanup has not been executed against a real lab; quickstart has not performed a fresh Windows installation here.

## Historical guest/runtime evidence

The original lab independently verified the following before extraction into this framework. These are historical acceptance observations, not claims that the new portable installer has already reproduced them:

- Windows 11 Pro x64 26300.9457 on dev and target, TPM ready, dev Secure Boot on and target off; target test signing and serial kernel debugging enabled.
- EWDK 28000.3231, Visual Studio Build Tools 18.8.3 and MSBuild 18.8.2. KMDF minor 33 for the example.
- The custom bounded IOCTL compiled, signed and deployed. Four negative cases and two deterministic positive cases passed; ordinary Echo I/O remained functional.
- Two named kernel breakpoint hits, typed response inspection, KMDF/`NtDeviceIoControlFile` stack, matching trace messages and final kernel globals were observed in live KD with the private PDB.
- Historical signed SYS SHA256: `8a40dd522ca59b5f41b99582a6917d25eb40e2a2515d2c1bb18d49da99adb454`.
- Historical PDB SHA256: `3f912aa003743885c464089f8ab906dbc6a9b4dce2b323c3cf972f8744c1d36f`.
- A prior paired checkpoint restore, targeted Verifier and dump analysis were tested on the original baseline. They were not repeated for the portable recovery implementation or every custom-driver revision.

Raw private transcripts, VM state, signed packages and memory artifacts are not distributed. Rebuilding may change binary hashes because of signing keys, timestamps and build paths. Reproducibility here means pinned inputs, repeatable operations, explicit identities and verifiable evidence, not byte-identical licensed Windows disks or signed binaries.

## Fresh-instance acceptance still required

On a new dedicated host/instance, follow INSTALL.md and record media hashes, dependency/firmware versions, install screenshots, bootstrap/access/TPM/Secure Boot checks, toolchain versions, positive/negative probe output, matching loaded SYS/PDB, live KD observations and a cold paired restore. Exercise full backup restoration on disposable data before treating it as disaster-recovery assurance. Keep those results separate from historical evidence.

A successful example does not prove all kernel projects, all Windows builds or all hypervisor configurations will work. Generalize only the workflows that have been tested and document new project-specific acceptance criteria.
