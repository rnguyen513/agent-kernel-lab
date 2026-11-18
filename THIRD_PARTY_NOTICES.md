# Third-party notices

`examples/observable-echo/kmdf` derives from Microsoft's Windows-driver-samples, `general/echo/kmdf`, revision `d49bb7d72f3651952b2b6e4ad28d14fe2247eb69`.

- Upstream: https://github.com/microsoft/Windows-driver-samples/tree/d49bb7d72f3651952b2b6e4ad28d14fe2247eb69/general/echo/kmdf
- License: Microsoft Public License (MS-PL), reproduced in `examples/observable-echo/LICENSE`.
- Original copyright notices are preserved. The custom changes add a bounded buffered IOCTL, deterministic response, trace/counter checkpoint and user-mode positive/negative probes. Those derivative sample changes are distributed under MS-PL as well.

The framework's MIT license does not replace the sample's MS-PL. Windows, EWDK, Win32-OpenSSH binaries, firmware and other host tools are not included in source releases and retain their respective licenses. Generated driver packages may contain local copies of WDK tools for lab deployment; they are excluded from this distributable source package.
