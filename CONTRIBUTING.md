# Contributing

Keep host code compatible with Python 3.10 and Ubuntu's packaged libvirt bindings. Use argv-based subprocesses, explicit instance ownership checks and fail-closed lifecycle guards. Guest helpers target Windows PowerShell 5.1. Do not add model-provider dependencies to the core command interface.

Run `python3 -m unittest discover -s tests -v`. Add meaningful regression tests for changed lifecycle, recovery, transport and publication behavior. Parse rendered PowerShell scripts using `tools/check-powershell.ps1`. Real Windows provisioning tests require operator-supplied licensed media and a dedicated disposable instance; never run them automatically against an existing lab.

Update docs/VALIDATION.md to distinguish mocked tests, real host-tool checks and actual guest execution. A deterministic source archive does not mean Windows installations or signed binaries are bit-for-bit deterministic. Preserve upstream attribution and the separate MS-PL license for sample derivatives.

Use `python3 tools/release.py` to create the reviewable source archive. Inspect its manifest before publishing. Local runtime and evidence must stay out of version control.
