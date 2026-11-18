# Observable Echo example

This MS-PL derivative of Microsoft's Echo AutoSync sample adds `IOCTL_WKL_PROBE` (function 0x800, METHOD_BUFFERED, read/write access). The fixed-size request is 16 bytes and response 32 bytes. It performs a bounded arithmetic transformation, with no arbitrary memory access primitive:

`output = ((input XOR 0x574B4C5F50524F42) + 0x1234) mod 2^64`

The response includes version, build marker `0x20261118`, input, output and a per-load call counter. The driver emits a trace and enters non-inlined `WklProbeCheckpoint`, allowing an agent to inspect a named function, typed response, globals and call stack in live KD.

`echoapp.exe -Probe` checks:

| Case | Expected result |
|---|---|
| Short input | Win32 error 122, zero returned bytes |
| Short output | Win32 error 122, zero returned bytes |
| Unsupported version | Win32 error 87, zero returned bytes |
| Unknown IOCTL | Win32 error 1, zero returned bytes |
| Input `1122334455667788` | Output `46697f1b05344afe`, 32 bytes |
| Input `0102030405060708` | Output `56494f5b55545a7e`, 32 bytes |

The valid calls have consecutive counters; the first pair after a fresh driver load is 1 and 2. Ordinary Echo I/O still exercises its 512/30720-byte paths. The project profile builds `driver/AutoSync/echo.vcxproj` and `exe/echoapp.vcxproj`; DriverSync is retained as upstream source but not built by this profile.

See [the workflow](../../docs/WORKFLOW.md) for KD commands and [validation scope](../../docs/VALIDATION.md) for historical observations. Matching source does not imply a newly signed binary will reproduce the historical hash: signing keys, timestamps and build paths can change it.
