"""Read-only guest inventory for the ORN Alpine sandbox.

Run from the repository root:
    python scripts/alpine_orn_guest_inventory.py

The script does not start, stop, mount, format, or modify the guest.
"""

from __future__ import annotations

import sys

from engine.tools.qemu_daemon import QemuDaemon


def main() -> int:
    daemon = QemuDaemon()
    status = daemon.status()
    print(f"QEMU status: {status.summary()}")

    if not status.online:
        print("Guest inventory skipped: start the sandbox first.")
        return 2

    command = r"""
echo '=== ALPINE RELEASE ==='
cat /etc/alpine-release 2>/dev/null || true
echo '=== KERNEL ==='
uname -a
echo '=== CPU ==='
grep -m1 -E 'model name|Processor|Hardware' /proc/cpuinfo 2>/dev/null || true
echo '=== MEMORY ==='
free -h
echo '=== FILESYSTEM SPACE ==='
df -h
echo '=== BLOCK DEVICES ==='
if command -v lsblk >/dev/null 2>&1; then lsblk -f; else cat /proc/partitions; fi
echo '=== MOUNTS ==='
mount
echo '=== FSTAB ==='
cat /etc/fstab 2>/dev/null || echo '(no /etc/fstab)'
echo '=== PERSISTENCE SENTINEL ==='
if [ -f /workspace/.orn_alpine_persistence_probe ]; then
    cat /workspace/.orn_alpine_persistence_probe
else
    echo '(sentinel not present; script did not create it)'
fi
"""
    output = daemon.shell(command, timeout=25)
    print(output)
    if output.startswith("(socket fechado") or output.startswith("(erro:"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
