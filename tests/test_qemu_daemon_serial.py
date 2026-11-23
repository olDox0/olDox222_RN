import logging
import socket

import pytest

import engine.tools.qemu_daemon as qemu_daemon


@pytest.mark.parametrize(
    "prompt",
    [
        b"localhost:~# ",
        b"localhost:/# ",
        b"localhost:/tmp/cysys-linux-test# ",
        b"node-1:/opt/orn# ",
        b"localhost:/tmp$ ",
    ],
)
def test_shell_prompt_recognizes_alpine_root_and_user_prompts(prompt: bytes) -> None:
    assert qemu_daemon._has_shell_prompt(prompt)


@pytest.mark.parametrize(
    "output",
    [
        b"",
        b"localhost login:",
        b"Welcome to Alpine Linux",
        b"localhost:/#\nnot-a-prompt",
        b"some ordinary output",
    ],
)
def test_shell_prompt_rejects_non_prompt_output(output: bytes) -> None:
    assert not qemu_daemon._has_shell_prompt(output)


def test_shell_prompt_uses_last_line() -> None:
    assert qemu_daemon._has_shell_prompt(
        b"previous output\r\nlocalhost:/tmp/work-dir# "
    )


class _ScriptedSocket:
    def __init__(self, events: list[bytes | BaseException]) -> None:
        self.events = list(events)
        self.sent: list[bytes] = []
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def recv(self, _size: int) -> bytes:
        if not self.events:
            raise socket.timeout()
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event

    def sendall(self, data: bytes) -> None:
        if self.closed:
            raise OSError("socket closed")
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


def _daemon() -> qemu_daemon.QemuDaemon:
    daemon = qemu_daemon.QemuDaemon.__new__(qemu_daemon.QemuDaemon)
    daemon.log = logging.getLogger("test.qemu_daemon")
    daemon._sock = None
    return daemon


def test_open_serial_accepts_prompt_with_persistent_working_directory(monkeypatch) -> None:
    sock = _ScriptedSocket([socket.timeout(), b"localhost:/tmp/cysys-linux-test# "])
    monkeypatch.setattr(qemu_daemon.socket, "create_connection", lambda *_a, **_k: sock)
    monkeypatch.setattr(qemu_daemon.time, "sleep", lambda _seconds: None)

    result = _daemon()._open_serial(8373, timeout=0.5)

    assert result is sock
    assert any(b"stty -echo" in sent for sent in sock.sent)


def test_open_serial_submits_root_login_once_and_recognizes_prompt(monkeypatch) -> None:
    sock = _ScriptedSocket(
        [
            socket.timeout(),
            b"localhost login:",
            b"localhost:/root# ",
        ]
    )
    monkeypatch.setattr(qemu_daemon.socket, "create_connection", lambda *_a, **_k: sock)
    monkeypatch.setattr(qemu_daemon.time, "sleep", lambda _seconds: None)

    result = _daemon()._open_serial(8373, timeout=0.5)

    assert result is sock
    assert sock.sent.count(b"root\n") == 1


class _HealthSocket(_ScriptedSocket):
    def __init__(self, *, reply: bool, echo_only: bool = False) -> None:
        super().__init__([])
        self.reply = reply
        self.echo_only = echo_only

    def sendall(self, data: bytes) -> None:
        super().sendall(data)
        if data.startswith(b"echo "):
            if self.reply:
                marker = data[5:].strip()
                self.events.append(marker + b"\r\n")
            elif self.echo_only:
                self.events.append(data.replace(b"\n", b"\r\n"))


def test_serial_socket_health_requires_command_output(monkeypatch) -> None:
    daemon = _daemon()
    monkeypatch.setattr(qemu_daemon.time, "monotonic_ns", lambda: 12345)

    assert daemon._serial_socket_healthy(_HealthSocket(reply=True), timeout=0.05)
    assert not daemon._serial_socket_healthy(_HealthSocket(reply=False), timeout=0.05)
    # Echo do TTY não comprova que o shell executou o comando.
    assert not daemon._serial_socket_healthy(
        _HealthSocket(reply=False, echo_only=True), timeout=0.05
    )


def test_ensure_socket_discards_stale_socket_and_reconnects() -> None:
    daemon = _daemon()
    stale = _HealthSocket(reply=False)
    replacement = _HealthSocket(reply=True)
    daemon._sock = stale
    daemon.status = lambda: type(
        "Status",
        (),
        {"online": True, "port": 8373, "summary": lambda self: "online"},
    )()
    daemon._open_serial = lambda _port: replacement
    daemon._serial_socket_healthy = lambda _sock: False

    assert daemon._ensure_socket()
    assert stale.closed
    assert daemon._sock is replacement
