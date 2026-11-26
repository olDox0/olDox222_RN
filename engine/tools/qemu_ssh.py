"""OpenSSH interativo entre Windows e o Alpine/QEMU do ORN.

O QEMU encaminha somente 127.0.0.1:<host-port> para a porta 22 do guest.
A primeira conexão usa TOFU (StrictHostKeyChecking=accept-new); mudanças
posteriores na chave do host são rejeitadas pelo OpenSSH.
"""
from __future__ import annotations

import base64
import os
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SSH_HOST = "127.0.0.1"
SSH_GUEST_PORT = 22
DEFAULT_SSH_HOST_PORT = 2222
SSH_SETUP_MARKER = "__ORN_SSH_SETUP_OK__"


def resolve_ssh_port(value: str | int | None = None) -> int:
    """Resolve ORN_QEMU_SSH_PORT e valida uma porta TCP não privilegiada."""
    raw: str | int | None = value
    if raw is None:
        raw = os.environ.get("ORN_QEMU_SSH_PORT", str(DEFAULT_SSH_HOST_PORT))
    try:
        port = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Porta SSH inválida: {raw!r}") from exc
    if not 1024 <= port <= 65535:
        raise ValueError(
            f"Porta SSH fora do intervalo permitido (1024–65535): {port}"
        )
    return port


def qemu_user_netdev(port: str | int | None = None) -> str:
    """Configura NAT QEMU e encaminha SSH exclusivamente pelo loopback do host."""
    host_port = resolve_ssh_port(port)
    return (
        f"user,id=net0,hostfwd=tcp:{SSH_HOST}:{host_port}-:{SSH_GUEST_PORT}"
    )


@dataclass(frozen=True)
class SSHPaths:
    state_dir: Path

    @property
    def key_dir(self) -> Path:
        return self.state_dir / "ssh"

    @property
    def private_key(self) -> Path:
        return self.key_dir / "id_ed25519"

    @property
    def public_key(self) -> Path:
        return self.key_dir / "id_ed25519.pub"

    @property
    def known_hosts(self) -> Path:
        return self.key_dir / "known_hosts"


class QemuSSHClient:
    """Provisiona o sshd do guest e abre uma sessão SSH com TTY real."""

    def __init__(
        self,
        state_dir: str | Path = "data/sandbox",
        port: str | int | None = None,
        host: str = SSH_HOST,
        username: str = "root",
        ssh_binary: str | None = None,
        ssh_keygen_binary: str | None = None,
    ) -> None:
        self.paths = SSHPaths(Path(state_dir))
        self.host = host
        self.port = resolve_ssh_port(port)
        self.username = username
        self._ssh_binary = ssh_binary
        self._ssh_keygen_binary = ssh_keygen_binary

    def ssh_executable(self) -> str:
        binary = self._ssh_binary or shutil.which("ssh")
        if not binary:
            raise RuntimeError(
                "Cliente OpenSSH não encontrado. No Windows, instale "
                "'OpenSSH Client' em Configurações > Sistema > Recursos opcionais."
            )
        return binary

    def ssh_keygen_executable(self) -> str:
        binary = self._ssh_keygen_binary or shutil.which("ssh-keygen")
        if not binary:
            raise RuntimeError(
                "ssh-keygen não encontrado. Instale o recurso Windows "
                "'OpenSSH Client' e confirme que ssh-keygen.exe está no PATH."
            )
        return binary

    def require_ssh_tools(self) -> None:
        self.ssh_executable()
        self.ssh_keygen_executable()

    @staticmethod
    def validate_public_key(public_key: str) -> str:
        """Aceita somente uma chave pública Ed25519 em uma única linha."""
        key = public_key.strip()
        parts = key.split()
        if (
            len(parts) < 2
            or parts[0] != "ssh-ed25519"
            or "\n" in key
            or "\r" in key
        ):
            raise ValueError("A chave pública ORN deve ser uma chave ssh-ed25519 válida.")
        return key

    def ensure_client_key(self) -> str:
        self.paths.key_dir.mkdir(parents=True, exist_ok=True)
        private_key = self.paths.private_key
        public_key = self.paths.public_key

        if private_key.exists() != public_key.exists():
            raise RuntimeError(
                f"Par de chaves incompleto em {self.paths.key_dir}. "
                "Restaure os dois arquivos ou mova o diretório para gerar outro par."
            )

        if not private_key.exists():
            subprocess.run(
                [
                    self.ssh_keygen_executable(),
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "orn-alpine-terminal",
                    "-f",
                    str(private_key),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        key = self.validate_public_key(
            public_key.read_text(encoding="utf-8")
        )
        if os.name != "nt":
            private_key.chmod(0o600)
        return key

    def wait_for_forward(self, timeout: float = 3.0) -> bool:
        """Confirma que o host-port encaminhado pelo QEMU está aceitando TCP."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=0.35
                ):
                    return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.1)

    def wait_for_ssh(self, timeout: float = 5.0) -> bool:
        """Confirma o banner SSH do guest, não apenas uma porta TCP aberta."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=0.5
                ) as connection:
                    connection.settimeout(0.8)
                    banner = connection.recv(255)
                    if banner.startswith(b"SSH-"):
                        return True
            except OSError:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def _guest_setup_script(self, public_key: str) -> str:
        key = self.validate_public_key(public_key)
        quoted_key = shlex.quote(key)
        return f"""set -eu
if ! apk info -e openssh-server >/dev/null 2>&1 || ! apk info -e openssh-server-common-openrc >/dev/null 2>&1; then
    apk add --no-cache openssh-server openssh-server-common-openrc
fi
install -d -m 700 /root/.ssh /etc/ssh/sshd_config.d
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
chown root:root /root/.ssh /root/.ssh/authorized_keys
if ! grep -Fqx -- {quoted_key} /root/.ssh/authorized_keys; then
    printf '%s\\n' {quoted_key} >> /root/.ssh/authorized_keys
fi
if ! grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config; then
    tmp=$(mktemp)
    printf 'Include /etc/ssh/sshd_config.d/*.conf\\n' > "$tmp"
    cat /etc/ssh/sshd_config >> "$tmp"
    mv "$tmp" /etc/ssh/sshd_config
fi
cat > /etc/ssh/sshd_config.d/00-orn-terminal.conf <<'ORN_SSH_CONF'
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AllowUsers root
ORN_SSH_CONF
ssh-keygen -A
/usr/sbin/sshd -t
rc-update add sshd default >/dev/null 2>&1 || true
if rc-service sshd status >/dev/null 2>&1; then
    rc-service sshd reload >/dev/null 2>&1 || rc-service sshd restart
else
    rc-service sshd start
fi
/usr/sbin/sshd -T | grep -E '^(permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication) '
printf '%s\\n' '__ORN_SSH_SETUP_OK__'
"""

    def configure_guest(self, daemon: Any, public_key: str) -> str:
        """Instala sshd, cadastra a chave e aplica política sem senha."""
        script = self._guest_setup_script(public_key)
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        command = f"printf '%s' {shlex.quote(encoded)} | base64 -d | sh"
        output = daemon.shell(command, timeout=120)
        if SSH_SETUP_MARKER not in output:
            raise RuntimeError(
                "O script do sshd não confirmou a configuração. "
                f"Saída do guest: {output[-1200:]}"
            )
        return output

    def build_ssh_command(self) -> list[str]:
        """Monta SSH com TTY, chave dedicada e verificação TOFU de host key."""
        return [
            self.ssh_executable(),
            "-tt",
            "-p",
            str(self.port),
            "-i",
            str(self.paths.private_key.resolve()),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            f"UserKnownHostsFile={self.paths.known_hosts.resolve()}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            f"{self.username}@{self.host}",
        ]

    def open_terminal(self) -> int:
        self.paths.key_dir.mkdir(parents=True, exist_ok=True)
        return subprocess.call(self.build_ssh_command())
