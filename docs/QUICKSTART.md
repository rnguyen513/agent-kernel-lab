# Guided quick start

From a Linux checkout, run the wizard as your ordinary user:

```sh
bash quickstart.sh
```

You need Python 3.10+, hardware KVM, enough memory for the configured guests, a mounted storage volume with at least 300 GiB free, and three downloaded files: Windows 11 Pro x64 en-US ISO, EWDK ISO and the Microsoft Win32-OpenSSH x64 ZIP. Official download locations and reference hashes are in [media.lock.json](../media.lock.json) and [INSTALL.md](INSTALL.md).

The wizard asks for storage/runtime paths and media files, computes their SHA256 values, and writes a private `local/lab.json`. Those hashes pin the files you supply; obtain them from trusted sources and compare publisher hashes where available. The script does not download large licensed media or choose a Windows license for you.

It offers to install missing Ubuntu/Debian host dependencies, requests sudo only for host operations, checks the configured mount/tools, and asks you to accept the Windows media license before provisioning. Defaults allocate 24 GiB of guest RAM; allow host headroom. The configured storage subdirectory must be new. Choose a subnet that does not overlap other guests or VPNs.

## Resume installation

Each run advances at most one Windows setup boot:

1. The first run provisions the pair and starts target installation.
2. Inspect the printed console screenshot. If it shows the DVD's “press any key” prompt, use the exact bounded key command printed by the wizard. No graphical viewer or blind keyboard input is launched.
3. Re-run `bash quickstart.sh` after target bootstrap completes. The wizard checks target SSH readiness and starts dev installation.
4. After dev bootstrap completes, re-run it again. It verifies both guests, finalizes media, synchronizes helpers and configures the EWDK/debugger on dev.

A failed readiness check prints the console location and leaves the existing installation intact. A paused or stopped guest with a recorded installation start needs inspection; the wizard never resets its start marker or reinstalls it. Existing installed instances use the normal guarded `start` command. Interrupted guest-tool configuration is retried on the next run.

Windows setup completion is not kernel-development acceptance. Continue with the clean backup, target test-signing/debug configuration, symbol caching and acceptance checks in [INSTALL.md](INSTALL.md) and [WORKFLOW.md](WORKFLOW.md). Keep the watchdog in a separate supervised terminal while guests run. The wizard prints the relevant commands, with the chosen configuration path included.

## Configure without changing the host

For a configuration/hash-only run, with no sudo, package installation or VM operations:

```sh
bash quickstart.sh --configure-only \
  --config local/lab.json \
  --lab-id akl --subnet 192.168.231.0/24 \
  --workspace "$HOME/.misc/akl-runtime" \
  --mount /mnt/lab --storage /mnt/lab/.akl \
  --windows /mnt/downloads/windows.iso \
  --ewdk /mnt/downloads/ewdk.iso \
  --openssh /mnt/downloads/OpenSSH-Win64.zip
```

All paths can contain spaces; quote them in your shell. Missing options are prompted interactively. With an existing config, omit new-instance options:

```sh
bash quickstart.sh --config local/lab.json
```

The script refuses to overwrite or silently change an existing configuration. `--install-deps` permits dependency installation when tools are missing. `--accept-windows-eula` supplies explicit license acceptance for provisioning. An incomplete provisioning attempt still requires a deliberate resume confirmation.

Run `bash quickstart.sh --help` for all options. Both entry-point scripts resolve paths relative to their checkout and can be launched from another working directory.
