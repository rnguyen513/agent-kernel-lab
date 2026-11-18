# Development and agent workflow

## Establish state

Read `AGENTS.md`, the configured workspace's `state/handoff.json`, latest run results, and actual `status`. If a restore journal or watchdog fault exists, inspect it before touching VM state. Historical pass records do not prove the current driver or guest state. Keep the watchdog supervised while the guests run; stop it with Ctrl+C after shutting down. Watchdog messages can include unrelated host storage events and conservatively pause this lab only.

The normal command envelope is `{"ok":true,"action":"...","result":...}`. Operational errors return `{"ok":false,...}` on stderr with exit 1; interruption returns 130. Argument/help errors follow argparse conventions. Run one lifecycle/build operation at a time. `debug`, guest stimulus and read-only inspection may run concurrently. A model can call the CLI through its shell tool; no particular model provider, API key or SDK is required.

## Build, deploy, test

```sh
sudo python3 akl.py start
python3 akl.py cycle --deploy
# To build an edited Echo-compatible tree:
python3 akl.py cycle --source /absolute/path/to/kmdf --deploy
```

The cycle captures source hashes, rebuilds the AutoSync driver and test application with KMDF minor 33, test-signs SYS/catalog with a non-exportable dev certificate, and installs/updates exactly one `root\ECHO` device. It retains source ZIP, signed ZIP, PDB, hashes and logs under `workspace/runs/<UTC>-<id>/`. These artifacts are private runtime outputs, not source-release contents. Keep the complete directory for each run.

Native devcon exit 1 means reboot required, and the cycle reports failure rather than claiming the new driver executed. Detach KD, disconnect the runtime serial cable, reboot normally, reconnect when Windows/SSH is ready, then run `Test-Sample.ps1` and `Test-ObservableDriver.ps1` against the deployed package. Never turn a required reboot into a claimed pass.

The custom example checks short input/output, unsupported version and unknown IOCTL, followed by two deterministic valid probes. It also compares installed/package SYS hashes. `cycle` intentionally leaves `runtime_observed:false`: live kernel breakpoints, traces and private-symbol identity need their own evidence.

## Observe kernel execution

In a dedicated terminal/PTY:

```sh
python3 akl.py debug
```

If KD waits to reconnect, Ctrl+C may be needed for the initial break. Then:

```text
.reload
lmvm ECHO
.reload /f ECHO.sys
bu ECHO!WklProbeCheckpoint
g
```

Launch `python3 akl.py guest target --script guest/Test-ObservableDriver.ps1` in another terminal. At each breakpoint on x64:

```text
dt ECHO!_WKL_PROBE_RESPONSE @rcx
k
dd ECHO!gWklProbeCalls L1
g
```

Save the KD terminal transcript alongside the run. Check the module's loaded identity and matching private PDB, two named breakpoint hits, response fields, KMDF/`NtDeviceIoControlFile` stack frames and kernel trace output. The included [example guide](../examples/observable-echo/README.md) specifies expected values. Call counters increase across later invocations; 1 and 2 apply to the first probe after a fresh driver load.

KD pauses the whole target, including SSH. Start the target stimulus asynchronously; do not wait for SSH completion while holding the target at a breakpoint. Clear experiment breakpoints with `bc *`, issue `g`, then detach with **Ctrl+B, Enter**. `q` can leave a live target halted. Never claim shutdown/recovery readiness while KD still holds the target.

The launcher uses cached public symbols and `C:\Lab\Symbols` by default. Online symbol access requires a deliberate NAT maintenance window and `-OnlineSymbols`. Use `.reload` before the targeted Echo reload; module names can be case-sensitive. A Windows marketing/OS build need not equal the underlying kernel build shown in KD.

## Other driver projects

Use the same isolated target, EWDK and SSH transport for your own project. Prepare a guest PowerShell script, upload source files or an archive, and invoke MSBuild through `C:\Lab\Build-Driver.cmd`:

```powershell
$ErrorActionPreference='Stop'
& cmd.exe /d /c 'C:\Lab\Build-Driver.cmd C:\Lab\MyDriver\MyDriver.vcxproj /t:Rebuild /p:Configuration=Debug /p:Platform=x64 /p:SignMode=Off'
if ($LASTEXITCODE) { throw "Build failed: $LASTEXITCODE" }
```

Run it with `python3 akl.py guest dev --script local/Build-MyDriver.ps1`. Long commands belong in files because Windows SSH command-line lengths are limited. Driver-specific signing/package layout, installation, input validation and acceptance tests remain your project's responsibility. The Echo scripts do not constitute a generic installer for every driver type.

Transfer with `guest ROLE --upload FILE --destination C:/Lab/file` or `--download C:/Lab/file --destination LOCAL`. Remote paths intentionally allow only simple absolute paths with `/`, no spaces or shell metacharacters. Use a guest script to stage files with other names. Large dump relay avoids a host-local dump copy:

```sh
python3 akl.py guest target --download C:/Windows/MEMORY.DMP \
  --to-role dev --destination C:/Lab/MEMORY.DMP
python3 akl.py guest dev --script guest/Analyze-LabDump.ps1
```

`guest/Test-Verifier.ps1` is scoped to Echo for one boot. Inspect its parameters and save a clean checkpoint before enabling it. Do not apply Verifier indiscriminately to all drivers. Crash/dump tests are separate acceptance work; wait for dump completion and preserve analysis before restoring.

## End a session

Record source/build identities, exact evidence paths, pass/fail cases, debugger observations and unresolved issues. After resuming/detaching KD:

```sh
sudo python3 akl.py stop
sudo python3 akl.py checkpoint create experiment-accepted
sudo python3 akl.py handoff --note 'State what passed, what remains and the next concrete action'
```

Use a unique checkpoint label. Shut down the watchdog terminal and leave no unattended debugger or guest job. The handoff observes power/network and records evidence locations; it does not automatically infer test success.
