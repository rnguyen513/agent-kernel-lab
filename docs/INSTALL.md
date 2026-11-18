# Installation

## Host and media

Run `bash tools/install-host.sh` from an ordinary user account. Use scoped sudo for host lifecycle commands, not a root agent. The dependency script installs no graphical VM viewer. Use the distro `/usr/bin/python3` so apt-installed `libvirt` and `PIL` modules are visible.

Mount the storage volume before provisioning; make its parent directories traversable by the configured QEMU account. Defaults use Ubuntu's `libvirt-qemu:kvm`; other distributions may require different accounts and firmware packages. Never change permissions on unrelated user directories merely to make a VM boot. `doctor` reports host dependencies and mount visibility; it is not a guarantee that every firmware/security policy is compatible.

Create the configuration as shown in the README. Keep orchestration/runtime on the host and large VM/media files on the dedicated volume. Do not manually pre-create the configured storage subdirectory: `provision` refuses existing storage to avoid overwriting an installation. Keep the generated instance UUID stable. Configuration changes after provisioning require an explicit migration, not editing values and hoping existing VM identities follow.

Download your licensed **Windows 11 Pro x64 en-US** ISO from [Microsoft](https://www.microsoft.com/software-download/windows11), an [EWDK ISO](https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk), and the official [Win32-OpenSSH x64 ZIP](https://github.com/PowerShell/Win32-OpenSSH/releases). EWDK includes matched command-line build tools, SDK and WDK. Review the media licenses before accepting unattended setup. The generic Pro setup key in the answer template selects the edition; it does not activate Windows or grant a license.

`media.lock.json` records the exact reference build, hashes and provenance. The reference SSH release is explicitly a preview, not a production server recommendation. If using another signed release, record its actual SHA256 and revalidate installation and transport. The bootstrap verifies the supplied hash and Microsoft signatures.

Populate `media` in `local/lab.json` with absolute paths and 64-character SHA256 values:

```json
"media": {
  "windows": {"path": "/mnt/media/windows.iso", "sha256": "REPLACE_WITH_ACTUAL_SHA256"},
  "ewdk": {"path": "/mnt/media/ewdk.iso", "sha256": "REPLACE_WITH_ACTUAL_SHA256"},
  "openssh": {"path": "/mnt/media/OpenSSH-Win64.zip", "sha256": "REPLACE_WITH_ACTUAL_SHA256"}
}
```

Use `sha256sum` locally, then compare with official published hashes where available. Reference Windows/EWDK digests are recorded download/readback evidence, not an independent publisher attestation. Signed Windows download URLs expire; do not commit them. `media-verify` checks all bytes before provisioning. Provisioning copies media to the storage volume, so allow room for both original downloads and staged copies.

## Provision and install

```sh
python3 akl.py media-verify
sudo python3 akl.py doctor
sudo python3 akl.py provision --accept-windows-eula
sudo python3 akl.py install-start target
sudo python3 akl.py console target
```

Inspect the saved screenshot using your agent's image reader. If the Windows DVD says to press a key, put `[{"action":"key","keys":"enter"},{"action":"wait","seconds":1},{"action":"screenshot"}]` in `local/boot-key.json` and run:

```sh
sudo python3 akl.py console target --actions local/boot-key.json
```

Do not send blind boot-menu sequences. Setup wipes **only the newly created guest disk**, creates the local lab account, then installs/configures SSH at first logon. Target firmware starts without enrolled Secure Boot keys; dev starts with Secure Boot enabled. Both use TPM 2.0. Expect several minutes on an SSD and longer on USB HDDs. Inspect screenshots and storage errors if progress stalls.

Wait for target SSH/bootstrap readiness:

```sh
python3 akl.py guest target --script guest/Inspect-Guest.ps1
sudo python3 akl.py install-start dev
sudo python3 akl.py console dev
```

Inspect dev's DVD prompt and send the same bounded action only if needed. Dev's serial connection stays disconnected during setup to avoid UEFI consuming debug traffic. After both guests report bootstrap readiness:

```sh
python3 akl.py guest dev --script guest/Inspect-Guest.ps1
sudo python3 akl.py install-finalize
python3 akl.py sync-tools both
python3 akl.py guest dev --script guest/Configure-Development.ps1
python3 akl.py guest dev --script guest/Inspect-Access.ps1
python3 akl.py guest target --script guest/Inspect-Access.ps1
sudo python3 akl.py stop
sudo python3 akl.py backup create clean-windows
```

Finalization checks names, completed setup, TPM and Secure Boot, persists actual firmware paths, ejects setup/seed media and attaches EWDK to dev. Recovery passwords and seed media remain private local recovery material. Bootstrap disables automatic logon and password SSH; access checks must confirm that before declaring setup accepted.

`--resume` is only for the exact recorded incomplete **provisioning** attempt before installation. It does not reinstall Windows or repair a partially completed guest setup. Once `install-start` has recorded a start, inspect the existing guest instead of invoking it again. Do not delete ownership/start journals to force a retry.

## Configure development and debugging

```sh
sudo python3 akl.py start
python3 akl.py guest target --command '& C:\Lab\Configure-Target.ps1 -EnableTestSigning'
sudo python3 akl.py stop
sudo python3 akl.py start
```

The target helper checks that it is the intended QEMU VM, Secure Boot is off and BitLocker protection is not active before changing boot debugging/test signing. It enables COM1 at 115200 and kernel dumps. A cold restart applies boot changes through the serial-safe startup sequence. Do not disable Secure Boot on dev.

Cache public symbols during an explicit maintenance window. Both guests must be off before changing network mode:

```sh
sudo python3 akl.py stop
sudo python3 akl.py network nat
sudo python3 akl.py start
python3 akl.py guest dev --script guest/Cache-Symbols.ps1
sudo python3 akl.py stop
sudo python3 akl.py network isolated
sudo python3 akl.py checkpoint create kernel-ready
```

The caching helper uses dev's kernel/HAL/KMDF binaries. When target versions differ, transfer target binaries to dev and cache their matching symbols; do not assume dev's cache covers target. Verify module/PDB identity in KD. Apply updates deliberately because they change the reference OS and symbols; record new versions and create a new accepted baseline.

Finish the acceptance steps in [WORKFLOW.md](WORKFLOW.md). Windows activation remains the operator's responsibility.
