#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst python3-libvirt python3-pil openssh-client git curl p7zip-full ovmf swtpm swtpm-tools genisoimage
sudo systemctl enable --now libvirtd
echo 'Host packages installed. Run akl.py with scoped sudo for system libvirt operations.'
