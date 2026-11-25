"""Testes unitários do terminal SSH Alpine/QEMU do ORN."""

from __future__ import annotations

import base64
import shlex
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from engine.tools.qemu_ssh import (
    DEFAULT_SSH_HOST_PORT,
    SSH_SETUP_MARKER,
    QemuSSHClient,
    qemu_user_netdev,
    resolve_ssh_port,
)


def test_ssh_port_defaults_to_loopback_port(monkeypatch) -> None:
    monkeypatch.delenv("ORN_QEMU_SSH_PORT", raising=False)
    assert resolve_ssh_port() == DEFAULT_SSH_HOST_PORT
    assert qemu_user_netdev() == (
        f"user,id=net0,hostfwd=tcp:127.0.0.1:{DEFAULT_SSH_HOST_PORT}-:22"
    )


def test_ssh_port_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("ORN_QEMU_SSH_PORT", "2322")
    assert resolve_ssh_port() == 2322
    assert "127.0.0.1:2322-:22" in qemu_user_netdev()


@pytest.mark.parametrize("value", ["abc", "", 22, 1023, 65536, -1])
def test_ssh_port_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError):
        resolve_ssh_port(value)


def test_ensure_client_key_creates_ed25519_pair(
    monkeypatch, tmp_path: Path
) -> None:
    client = QemuSSHClient(state_dir=tmp_path, ssh_keygen_binary="ssh-keygen")

    def fake_run(args, **kwargs):
        private_key = Path(args[args.index("-f") + 1])
        private_key.write_text("private-key", encoding="utf-8")
        Path(str(private_key) + ".pub").write_text(
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest orn-test\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    public_key = client.ensure_client_key()

    assert public_key.startswith("ssh-ed25519 ")
    assert client.paths.private_key.is_file()
    assert client.paths.public_key.is_file()


def test_ensure_client_key_rejects_partial_pair(tmp_path: Path) -> None:
    client = QemuSSHClient(state_dir=tmp_path, ssh_keygen_binary="ssh-keygen")
    client.paths.key_dir.mkdir(parents=True)
    client.paths.private_key.write_text("private", encoding="utf-8")

    with pytest.raises(RuntimeError, match="incompleto"):
        client.ensure_client_key()


def test_guest_setup_is_base64_wrapped_and_checks_marker(tmp_path: Path) -> None:
    client = QemuSSHClient(state_dir=tmp_path)
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest orn-test"

    class FakeDaemon:
        command = ""
        timeout = 0

        def shell(self, command: str, timeout: float):
            self.command = command
            self.timeout = timeout
            return "passwordauthentication no\n" + SSH_SETUP_MARKER

    daemon = FakeDaemon()
    output = client.configure_guest(daemon, public_key)
    command_parts = shlex.split(daemon.command)
    encoded = command_parts[2]
    script = base64.b64decode(encoded).decode("utf-8")

    assert output.endswith(SSH_SETUP_MARKER)
    assert daemon.timeout == 120
    assert "PasswordAuthentication no" in script
    assert "PermitRootLogin prohibit-password" in script
    assert public_key in script
    assert "rc-service sshd" in script


def test_guest_setup_fails_without_success_marker(tmp_path: Path) -> None:
    client = QemuSSHClient(state_dir=tmp_path)

    class FakeDaemon:
        def shell(self, _command: str, timeout: float):
            return "apk failed"

    with pytest.raises(RuntimeError, match="não confirmou"):
        client.configure_guest(
            FakeDaemon(),
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest orn-test",
        )


def test_ssh_command_forces_tty_and_pins_known_hosts(tmp_path: Path) -> None:
    client = QemuSSHClient(
        state_dir=tmp_path,
        port=2228,
        ssh_binary="ssh.exe",
    )
    command = client.build_ssh_command()

    assert command[0] == "ssh.exe"
    assert "-tt" in command
    assert command[command.index("-p") + 1] == "2228"
    assert "StrictHostKeyChecking=accept-new" in command
    assert any(arg.startswith("UserKnownHostsFile=") for arg in command)
    assert command[-1] == "root@127.0.0.1"


def test_wait_for_forward_detects_local_listener(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = QemuSSHClient(state_dir=tmp_path, port=port)

    try:
        assert client.wait_for_forward(timeout=0.3) is True
    finally:
        listener.close()


def test_wait_for_ssh_requires_ssh_protocol_banner(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = QemuSSHClient(state_dir=tmp_path, port=port)

    def send_banner() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.sendall(b"SSH-2.0-OpenSSH_test\\r\\n")

    thread = threading.Thread(target=send_banner, daemon=True)
    thread.start()
    try:
        assert client.wait_for_ssh(timeout=2.0) is True
    finally:
        listener.close()
        thread.join(timeout=1.0)


def test_wait_for_ssh_rejects_non_ssh_service(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = QemuSSHClient(state_dir=tmp_path, port=port)

    def send_banner() -> None:
        connection, _ = listener.accept()
        with connection:
            connection.sendall(b"HTTP/1.1 200 OK\\r\\n")

    thread = threading.Thread(target=send_banner, daemon=True)
    thread.start()
    try:
        assert client.wait_for_ssh(timeout=0.5) is False
    finally:
        listener.close()
        thread.join(timeout=1.0)


def test_sandbox_terminal_command_is_registered() -> None:
    from engine.cli import cli

    sandbox_group = cli.commands["sandbox"]
    assert "terminal" in sandbox_group.commands
