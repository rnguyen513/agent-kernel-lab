# Security model

This is a local research tool operated by a trusted host user. Guest code and project builds execute with administrator privileges inside disposable research VMs. Host lifecycle commands require scoped root access. Configuration/ownership checks prevent common wrong-instance mistakes; they are not a security boundary against a malicious local operator or root process.

The default libvirt network has no NAT forwarding. Host and guests can still communicate; isolation is not an air gap or protection against a hypervisor vulnerability. Explicit NAT maintenance allows outbound connectivity. SSH permits the host bridge only, uses a per-instance key and disables password authentication. Initial SSH host keys use trust-on-first-use in a dedicated known_hosts file. Verify fingerprints through the console when stronger initial identity assurance is needed; never delete a changed-host-key warning without investigation.

Target test signing and disabled Secure Boot are deliberate development settings. Dev retains Secure Boot. There are no host shared folders, USB redirection or SPICE clipboard/file transfer in generated domains. The SPICE display listens only on loopback; headless control uses libvirt screenshots and input.

Protect the private workspace and seed ISOs: unattended setup necessarily embeds generated recovery passwords. Bootstrap disables autologon; finalization ejects seed media. Do not share raw guest disks, registry dumps, memory dumps, transcripts or build artifacts without reviewing their contents. The release builder uses an allowlist and excludes runtime directories. Its scan is a packaging guard, not a general-purpose secret detector.

Report a security issue privately to the repository owner once a repository/contact is established. Until then, do not post credentials, dumps or exploit details in public issue trackers. No hosted reporting endpoint is configured by this source package.
