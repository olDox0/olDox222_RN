# -*- coding: utf-8 -*-
"""QemuDaemon — Alpine QEMU persistente com observabilidade total.

Três fontes de evidência em paralelo:
  serial.log      → capturado pelo próprio QEMU (chardev logfile)
  qemu_trace.log  → eventos do emulador (-d int,guest_errors,cpu_reset)
  daemon.log      → ações do Python (handshake, sockets)
"""
from __future__ import annotations

import logging
import os, re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.tools.qemu_sandbox import QemuSandbox, SandboxResult

HOST = "127.0.0.1"
PORT_CANDIDATES = [8373, 8374, 8375, 8376]
STATE_DIR = Path("data/sandbox")
PID_FILE = STATE_DIR / "qemu_daemon.pid"
PORT_FILE = STATE_DIR / "qemu_daemon.port"
LOG_FILE = STATE_DIR / "qemu_daemon.log"        # stdout/stderr do QEMU
SERIAL_FILE = STATE_DIR / "serial.log"           # serial capturada pelo QEMU
TRACE_FILE = STATE_DIR / "qemu_trace.log"        # eventos do QEMU
DAEMON_LOG_FILE = STATE_DIR / "daemon.log"       # o que o Python faz
DISK_FILE = STATE_DIR / "alpine.img.qcow2"
DISK_SIZE_MB = 512

_SHELL_PROMPT_RE = re.compile(rb"[A-Za-z0-9_.-]+:[^\r\n]*[#$][ \t]*$")


def _has_shell_prompt(data: bytes) -> bool:
    """Reconhece o prompt final do ash/sh do Alpine, inclusive com cwd."""
    tail = data.rstrip(b"\r\n")
    if not tail:
        return False
    line = tail.rsplit(b"\n", 1)[-1].rstrip(b"\r")
    return _SHELL_PROMPT_RE.fullmatch(line) is not None


def _setup_logger() -> logging.Logger:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("orn.sandbox.daemon")
    # DEBUG só com ORN_DEBUG=1, INFO por padrão
    level = logging.DEBUG if os.environ.get("ORN_DEBUG") == "1" else logging.INFO
    logger.setLevel(level)
    if not logger.handlers:
        fh = logging.FileHandler(DAEMON_LOG_FILE, mode="a", encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)  # arquivo sempre debug
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(level)  # terminal só INFO
        logger.addHandler(sh)
    return logger


@dataclass
class DaemonStatus:
    pid_file_exists: bool
    pid: Optional[int]
    pid_alive: bool
    port_file_exists: bool
    port: Optional[int]
    port_responsive: bool

    @property
    def online(self) -> bool:
        return self.pid_alive and self.port_responsive

    def summary(self) -> str:
        if self.online:
            return f"online (PID {self.pid}, porta {self.port})"
        if not self.pid_file_exists:
            return "offline (sem PID file)"
        if not self.pid_alive:
            return f"offline (PID {self.pid} morto)"
        if not self.port_file_exists:
            return f"offline (PID {self.pid} vivo mas PORT ausente)"
        return f"offline (PID {self.pid} vivo, porta {self.port} não responde)"


class QemuDaemon:
    def __init__(self, alpine_root: str | Path = "data/sandbox/alpine") -> None:
        self.alpine_root = Path(alpine_root).resolve()
        self.qs = QemuSandbox(alpine_root)
        self.log = _setup_logger()
        self.boot_mode = "disk"
        self._process: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    # ── logs ───────────────────────────────────────────────
    def _tail(self, path: Path, n: int) -> str:
        if not path.exists():
            return f"({path.name} ausente)"
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except OSError as exc:
            return f"(erro lendo {path.name}: {exc})"

    def logs(self, n: int = 50, which: str = "qemu") -> str:
        mapping = {
            "qemu": LOG_FILE,
            "serial": SERIAL_FILE,
            "trace": TRACE_FILE,
            "daemon": DAEMON_LOG_FILE,
        }
        return self._tail(mapping.get(which, LOG_FILE), n)

    # ── estado ─────────────────────────────────────────────
    def _read_pid(self) -> Optional[int]:
        if not PID_FILE.exists():
            return None
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            return None

    def _read_port(self) -> Optional[int]:
        if not PORT_FILE.exists():
            return None
        try:
            return int(PORT_FILE.read_text().strip())
        except (ValueError, OSError):
            return None

    def _pid_alive(self, pid: int) -> bool:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return "qemu-system-x86_64.exe" in out.lower()
        except Exception:
            return False

    def _port_responds(
        self,
        port: int,
        timeout: float = 1.0,
        expected_pid: Optional[int] = None,
    ) -> bool:
        """Verifica a porta sem abrir conexão no canal serial."""
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.splitlines():
                parts = line.split()

                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue

                local_port = parts[1].rsplit(":", 1)[-1]
                state = parts[3].upper()
                process_id = parts[4]

                if local_port != str(port):
                    continue

                if state != "LISTENING":
                    continue

                if expected_pid is not None and process_id != str(expected_pid):
                    continue

                return True

            return False

        except Exception as exc:
            self.log.warning("_port_responds: erro verificando porta: %s", exc)
            return False

    def status(self) -> DaemonStatus:
        pid = self._read_pid()
        alive = pid is not None and self._pid_alive(pid)
        port = self._read_port()
        resp = (
            port is not None
            and pid is not None
            and self._port_responds(port, expected_pid=pid)
        )
        return DaemonStatus(
            pid_file_exists=PID_FILE.exists(), pid=pid, pid_alive=alive,
            port_file_exists=PORT_FILE.exists(), port=port, port_responsive=resp,
        )

    def is_running(self) -> bool:
        return self.status().online

    # ── helpers ────────────────────────────────────────────
    @staticmethod
    def _kill_stale_qemu() -> int:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq qemu-system-x86_64.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            pids: list[int] = []
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) >= 2 and parts[0].lower().startswith("qemu-system"):
                    try:
                        pids.append(int(parts[1]))
                    except ValueError:
                        pass
            for pid in pids:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
            return len(pids)
        except Exception:
            return 0

    @staticmethod
    def _port_is_free(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, port))
            return True
        except OSError:
            return False

    def _find_free_port(self) -> Optional[int]:
        for p in PORT_CANDIDATES:
            if self._port_is_free(p):
                return p
        return None

    # ── lifecycle ──────────────────────────────────────────
    def start(self, timeout: int = 180) -> bool:
        prev = self.status()
        if prev.online:
            self.log.info("start: daemon já rodando — %s", prev.summary())
            print(f"  [OK] Daemon já rodando ({prev.summary()}).")
            return True
        if prev.pid_file_exists and not prev.pid_alive:
            self.log.info("start: limpando PID morto %s", prev.pid)
            self._clean_state()

        # Retry geral do boot (se cair em recovery shell, tenta de novo)
        for attempt in range(1, 4):
            print(f"  [..] Tentativa de boot {attempt}/3...")
            if self._try_boot(timeout=timeout):
                return True
            # Mata o QEMU do attempt anterior (recovery shell)
            pid = self._read_pid()
            if pid and self._pid_alive(pid):
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        timeout=5,
                    )
                except Exception:
                    pass
            self._clean_state()
            #self._kill_stale_qemu()
            if attempt < 3:
                print(f"  [!]  Tentando de novo em 2s...")
                time.sleep(2)

        print("  [ERRO] 3 tentativas de boot falharam.")
        print(f"  [..] Veja 'orn sandbox probe -w serial' para o último log.")
        return False

    def _try_boot(self, timeout: int) -> bool:
        """Uma tentativa de boot completa (QEMU + login)."""
        killed = self._kill_stale_qemu()
        if killed:
            self.log.info("_try_boot: %d QEMU órfão encerrado", killed)
            time.sleep(1.5)

        port = self._find_free_port()
        if port is None:
            self.log.error("_try_boot: nenhuma porta livre")
            return False
        self.log.info("_try_boot: porta=%d", port)
        print(f"    [OK] Porta serial: {port}")

        if not self.qs.is_available():
            self.log.error("_try_boot: qemu ausente")
            return False

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for f in (SERIAL_FILE, TRACE_FILE):
            f.unlink(missing_ok=True)

        # Seleciona a mídia de boot. O disco QCOW2 mantém o Alpine instalado.
        iso_file = self.alpine_root / "alpine-virt.iso"
        boot_mode = getattr(self, "boot_mode", "disk").lower()

        if boot_mode not in ("disk", "iso"):
            self.log.error("_try_boot: modo inválido: %s", boot_mode)
            return False

        if boot_mode == "disk":
            if not DISK_FILE.is_file():
                self.log.error("_try_boot: disco persistente ausente: %s", DISK_FILE)
                return False
            boot_media = []
            boot_order = "c"
        else:
            if not iso_file.is_file():
                self.log.error("_try_boot: ISO de recuperação ausente: %s", iso_file)
                return False
            boot_media = ["-cdrom", str(iso_file)]
            boot_order = "d"

        self.log.info("_try_boot: boot_mode=%s", boot_mode)
        # Detecção de aceleração nativa para Windows com fallback TCG.

        accel_flags = ["-accel", "whpx", "-accel", "tcg"]

        cmd = [
            self.qs.qemu_exe,
            *accel_flags,
            "-m", "512M",
            "-smp", "2",
            # "-cdrom", str(iso_file),
            # "-boot", "d",
            *boot_media,
            "-boot", boot_order,
            "-chardev",
            f"socket,id=serial0,host={HOST},port={port},server=on,wait=off,"
            f"logfile={str(SERIAL_FILE.resolve()).replace(chr(92), '/')},logappend=off",
            "-serial", "chardev:serial0",
            *(["-drive",
               f"file={str(DISK_FILE.resolve()).replace(chr(92), '/')},"
               f"if=virtio,format=qcow2"]
              if DISK_FILE.exists() else []),
            "-D", str(TRACE_FILE.resolve()),
            "-d", "guest_errors,cpu_reset",
            "-monitor", "none",
            "-display", "none",
            "-netdev", "user,id=net0",
            "-device", "virtio-net-pci,netdev=net0",
            "-no-shutdown",
        ]
        self.log.info("_try_boot: cmd=%s", " ".join(cmd))

        log_fh = open(LOG_FILE, "w", encoding="utf-8")
        self._process = subprocess.Popen(
            cmd, cwd=os.path.dirname(self.qs.qemu_exe),
            stdin=subprocess.DEVNULL, stdout=log_fh, stderr=log_fh,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        log_fh.close()
        PID_FILE.write_text(str(self._process.pid))
        PORT_FILE.write_text(str(port))
        self.log.info("_try_boot: qemu PID=%d port=%d", self._process.pid, port)
        print(f"    [OK] QEMU iniciado (PID {self._process.pid})")

        deadline = time.time() + timeout
        boot_state = "unknown"
        last_log_size = -1
        import re

        while time.time() < deadline:
            if self._process.poll() is not None:
                self.log.error("_try_boot: qemu morreu exit=%s", self._process.returncode)
                return False

            if SERIAL_FILE.exists():
                size = SERIAL_FILE.stat().st_size
                if size != last_log_size:
                    last_log_size = size
                    try:
                        text = SERIAL_FILE.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        text = ""
                    low = text.lower()

                    if "emergency recovery shell" in low or "not found in new root" in low:
                        boot_state = "recovery"
                        self.log.warning("_try_boot: recovery shell detectado")
                        break

                    if (re.search(r"welcome to alpine linux\s+3\.", low) or
                        re.search(r"[a-z][a-z0-9\-]*:~\s*#", text) or
                        re.search(r"[a-z][a-z0-9\-]*:/\s*#", text)):
                        boot_state = "ok"
                        break

            time.sleep(1)

        if boot_state != "ok":
            return False

        print(f"    [OK] Boot completo detectado.")
        self._sock = self._open_serial(port, timeout=20.0)
        if self._sock is None:
            print(f"    [!] Boot OK, mas o shell serial não ficou pronto.")
            return False
        print(f"    [OK] Socket logado.")
        return True

    def _drain(self, s: socket.socket, wait: float = 0.2) -> bytes:
        buf = b""
        s.settimeout(wait)
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass
        return buf

    def _open_serial(self, port: int, timeout: float = 15.0) -> Optional[socket.socket]:
        try:
            s = socket.create_connection((HOST, port), timeout=5.0)
        except OSError as exc:
            self.log.error("open_serial: connect falhou: %s", exc)
            return None
        self.log.debug("open_serial: TCP conectado em %s:%d", HOST, port)
        
        # Envia Ctrl+C e Enter para matar qualquer processo travado que esteja monopolizando o terminal
        try:
            s.sendall(b"\x03\x03\n")
            time.sleep(0.2)
        except OSError:
            pass

        s.settimeout(0.15)
        drained = b""
        for _ in range(80):  
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                drained += chunk
            except socket.timeout:
                break
        if drained:
            self.log.debug("open_serial: drenou %d bytes", len(drained))
        try:
            s.sendall(b"\x03\n")
            time.sleep(0.3)
        except OSError:
            pass

        s.settimeout(1.5)
        deadline = time.time() + timeout
        got_prompt = False
        login_submitted = False
        buffer = b""
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                if b"login:" in buffer.lower() and not _has_shell_prompt(buffer):
                    if not login_submitted:
                        try:
                            s.sendall(b"root\n")
                            login_submitted = True
                        except OSError:
                            break
                else:
                    try:
                        # Se ainda não apareceu o prompt, manda Ctrl+C de novo
                        s.sendall(b"\x03\n")
                    except OSError:
                        break
                continue
            if not chunk:
                break
            buffer += chunk
            if _has_shell_prompt(buffer):
                got_prompt = True
                break
            if b"login:" in buffer.lower() and not login_submitted:
                try:
                    s.sendall(b"root\n")
                    login_submitted = True
                except OSError:
                    break
        if not got_prompt:
            self.log.warning(
                "open_serial: sem prompt em %ss (buf=%r)",
                timeout, buffer[-80:],
            )
            try:
                s.close()
            except Exception:
                pass
            return None
        try:
            s.sendall(b"stty -echo 2>/dev/null\n")
            time.sleep(0.2)
        except OSError:
            pass
        return s

    def _serial_socket_healthy(
        self, sock: socket.socket, timeout: float = 1.0
    ) -> bool:
        """Confirma execução de um comando no shell, não apenas escrita no TCP."""
        marker = f"__ORN_HEALTH_{time.monotonic_ns()}__".encode("ascii")
        marker_line = re.compile(
            rb"(?:^|\r?\n)" + re.escape(marker) + rb"(?:\r?\n|$)"
        )
        try:
            self._drain(sock, wait=0.1)
            sock.sendall(b"echo " + marker + b"\n")
            sock.settimeout(min(0.2, timeout))
            response = bytearray()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    return False
                response.extend(chunk)
                if marker_line.search(response):
                    return True
            return False
        except OSError as exc:
            self.log.debug("ensure_socket: health check falhou: %s", exc)
            return False

    def _ensure_socket(self) -> bool:
        if self._sock is not None:
            if self._serial_socket_healthy(self._sock):
                return True
            self.log.warning("ensure_socket: socket serial sem resposta válida")
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        st = self.status()
        if not st.online or st.port is None:
            self.log.warning("ensure_socket: daemon offline (%s)", st.summary())
            return False
        self._sock = self._open_serial(st.port)
        return self._sock is not None

    def _wait_boot_marker(self, port: int) -> bool:
        """Retorna True só se o Alpine estiver no sistema completo (não recovery)."""
        try:
            with socket.create_connection((HOST, port), timeout=2) as s:
                s.settimeout(1.5)
                buf = b""
                start = time.time()
                while time.time() - start < 4.0:
                    try:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                        text = buf.decode("utf-8", errors="replace")
                        low = text.lower()
                        if "emergency recovery" in low:
                            return False
                        if re.search(r"welcome to alpine linux\s+3\.", low):
                            return True
                        if _has_shell_prompt(buf):
                            return True
                    except socket.timeout:
                        break
        except OSError:
            pass
        return False

    def stop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        pid = self._read_pid()
        if pid and self._pid_alive(pid):
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
            except Exception:
                pass
        self._clean_state()
        #self._kill_stale_qemu()
        self._process = None
        self.log.info("stop: concluído")

    def _clean_state(self) -> None:
        PID_FILE.unlink(missing_ok=True)
        PORT_FILE.unlink(missing_ok=True)

    # ── shell / bootstrap / run ────────────────────────────
    def shell(self, cmd: str, timeout: float = 20.0) -> str:
        if not self._ensure_socket():
            return "(socket fechado: daemon offline ou login falhou)"
        with self._lock:
            try:
                self._drain(self._sock, wait=0.1)
                marker = f"__ORN_{int(time.time()*1000)}__"
                self._sock.sendall(f"{cmd}\necho {marker}\n".encode())
                buf = b""
                deadline = time.time() + timeout
                marker_bytes = marker.encode()
                while time.time() < deadline:
                    try:
                        chunk = self._sock.recv(8192)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    if marker_bytes in buf:
                        break
                text = buf.decode("utf-8", errors="replace")
                cleaned = []
                for raw_l in text.splitlines():
                    s = raw_l.strip().replace("\r", "")
                    if not s:
                        continue
                    if marker in s or s == cmd.strip() or f"echo {marker}" in s:
                        continue
                    if _has_shell_prompt(s.encode("utf-8", errors="replace")):
                        continue
                    cleaned.append(s)
                return "\n".join(cleaned).strip()
            except Exception as exc:
                self._sock = None
                return f"(erro: {exc})"

    def bootstrap(self) -> bool:
        if not self._ensure_socket():
            self.log.error("bootstrap: sem socket")
            print("  [ERRO] Socket fechado ou daemon offline. Rode 'orn sandbox daemon start'.")
            return False

        print("  [1/4] Verificando e ativando rede (eth0)...")
        # Levanta a interface e obtém IP do QEMU via DHCP
        self.shell("ip link set eth0 up", timeout=5)
        dhcp_out = self.shell("udhcpc -i eth0 -q -n -t 5 2>&1", timeout=15)
        print(f"    | DHCP: {dhcp_out}")

        ip_out = self.shell("ip -4 addr show eth0 2>&1", timeout=5)
        print(f"    | IP: {ip_out.strip()}")

        # Configura DNS confiável no resolv.conf
        self.shell("echo 'nameserver 8.8.8.8' > /etc/resolv.conf", timeout=5)

        # Teste de conectividade real
        ping_out = self.shell("ping -c 1 -W 2 8.8.8.8 2>&1", timeout=10)
        net_ok = "1 packets received" in ping_out or "1 received" in ping_out
        if net_ok:
            print("    [OK] Conectividade com a internet confirmada.")
        else:
            print(f"    [!] Aviso de ping (pode ser ICMP bloqueado pelo firewall host): {ping_out}")

        # Resolve o IP do CDN pelo host e injeta no /etc/hosts do Alpine
        try:
            cdn_ip = socket.gethostbyname("dl-cdn.alpinelinux.org")
        except Exception:
            cdn_ip = "151.101.18.132"

        print(f"  [2/4] Configurando DNS local ({cdn_ip}) e repositórios...")
        self.shell(f"echo '{cdn_ip} dl-cdn.alpinelinux.org' >> /etc/hosts", timeout=5)

        repo_cmds = (
            "mkdir -p /etc/apk && "
            "echo 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' > /etc/apk/repositories && "
            "echo 'https://dl-cdn.alpinelinux.org/alpine/v3.24/community' >> /etc/apk/repositories"
        )
        self.shell(repo_cmds, timeout=10)

        # Configuração dos Repositórios Oficiais
        print("  [2/4] Configurando repositórios em /etc/apk/repositories...")
        repo_cmds = (
            "mkdir -p /etc/apk"
        )
        self.shell(
            "echo 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' > /etc/apk/repositories",
            timeout=10,
        )
        self.shell(
            "echo 'https://dl-cdn.alpinelinux.org/alpine/v3.24/community' >> /etc/apk/repositories",
            timeout=10,
        )
        self.shell(repo_cmds, timeout=10)
        repos = self.shell("cat /etc/apk/repositories 2>&1", timeout=5)
        print(f"    | Repositórios ativos:\n{repos}")

        # Verificar se já temos o bootstrap flag gravado
        flag = self.shell("test -f /root/.orn_ready && echo Y || echo N", timeout=5)
        if "Y" in flag:
            print("  [OK] Bootstrap já instalado anteriormente (/root/.orn_ready presente).")
            return True

        # Atualização do índice de pacotes com saída transparente
        print("  [3/4] Atualizando índices (apk update)...")
        upd = ""
        upd_ok = False
        for attempt in range(1, 4):
            upd = self.shell("apk update --verbose 2>&1", timeout=60)
            print(f"    | Tentativa {attempt}/3:")
            for line in upd.splitlines():
                print(f"      {line}")
            if "OK:" in upd or "packages" in upd:
                upd_ok = True
                print(f"    [OK] Índices do Alpine atualizados.")
                break
            time.sleep(2)

        if not upd_ok:
            print("  [ERRO] 'apk update' falhou 3 vezes. Verifique a saída acima.")
            return False

        # Instalação do GCC, musl-dev, Python 3 e Pip
        print("  [4/4] Instalando gcc, musl-dev, python3, py3-pip...")
        inst = self.shell(
            "apk add --no-cache gcc musl-dev python3 py3-pip 2>&1",
            timeout=300,
        )
        print(f"    | Saída do instalador:\n{inst}")

        if "OK:" in inst or "100%" in inst:
            self.shell("touch /root/.orn_ready", timeout=5)
            print("  [OK] Bootstrap concluído com sucesso!")
            return True
        else:
            print("  [ERRO] Falha na instalação de pacotes. Veja a saída do instalador acima.")
            return False

    @staticmethod
    def _clean_output(text: str) -> str:
        """Remove prompts do Alpine, ecos de comando e ruído do serial."""
        import re
        if not text:
            return ""

        # 1. Remove prompts em QUALQUER posição
        text = re.sub(r"[a-zA-Z0-9_\-]+[:/][~/$]\s*#\s*", "", text)
        text = re.sub(r"root@[^\s:]+[:/][^\s]*#\s*", "", text)
        text = re.sub(r"(?m)^\s*#\s*", "", text)

        # 2. Remove comandos ecoados, marcadores e lixo do shell
        skip_prefixes = (
            "/tmp/app", "/tmp/main.c", "gcc ", "GCC_RC",
            "M_", "READY_", "ALIVE_", "MARK_",
            "cat > /tmp/main.c", "echo '===", "echo M_", "stty -echo",
            "EOF_", "localhost:", "root@", "rm -f /tmp/app",
            "if [", "else ", "then ", "fi", "}",
            "===COMPILANDO===", "===COMPILADO_OK===", "===COMPILE_FAILED===",
            "===EXECUTANDO===", "===FIM===",
        )
        out = []
        for line in text.splitlines():
            s = line.rstrip()
            if not s:
                continue
            if any(s.startswith(p) for p in skip_prefixes):
                continue
            if "M_" in s and "==" not in s:
                s = re.sub(r"\s*M_\d+\s*", "", s)
            if "READY_" in s:
                s = re.sub(r"\s*READY_\d+\s*", "", s)
            s = s.strip()
            if s:
                out.append(s)
        return "\n".join(out).strip()

    def run(self, code: str, args: Optional[list[str]] = None,
            timeout: int = 120, lang: str = "c") -> SandboxResult:
        """Executa código no Alpine. lang='c' (default) ou 'python'."""
        if lang == "python":
            return self._run_python(code, args, timeout)
        return self._run_c(code, args, timeout)

    def _run_c(self, code: str, args: Optional[list[str]],
               timeout: int) -> SandboxResult:
        if not self._ensure_socket():
            return SandboxResult(False, "", "Daemon offline ou socket morto", -2)

        args = args or []
        import shlex
        args_str = " ".join(shlex.quote(a) for a in args)
        eof = f"EOF_{int(time.time()*1000)}"

        with self._lock:
            try:
                self._drain(self._sock, wait=0.05)
                run_sec = max(5, timeout - 5)
                payload = (
                    f"killall -9 app 2>/dev/null\n"
                    f"cat << '{eof}' > /tmp/main.c\n"
                    f"{code}\n"
                    f"{eof}\n"
                    f"rm -f /tmp/app /tmp/out.txt /tmp/err.txt\n"
                    f"gcc -O2 /tmp/main.c -o /tmp/app > /tmp/err.txt 2>&1\n"
                    f"GCC_RC=$?\n"
                    f"if [ $GCC_RC -ne 0 ]; then\n"
                    f"  echo '===COMPILE_FAILED==='\n"
                    f"  cat /tmp/err.txt\n"
                    f"  echo '===FIM==='\n"
                    f"else\n"
                    f"  echo '===EXECUTANDO==='\n"
                    f"  timeout {run_sec} /tmp/app {args_str} > /tmp/out.txt 2>&1\n"
                    f"  APP_RC=$?\n"
                    f"  if [ $APP_RC -eq 143 ] || [ $APP_RC -eq 137 ] || [ $APP_RC -eq 124 ]; then\n"
                    f"    echo 'Erro: Execução excedeu o tempo limite (possível loop infinito).' >> /tmp/out.txt\n"
                    f"  fi\n"
                    f"  echo \"APP_RC=$APP_RC\"\n"
                    f"  cat /tmp/out.txt\n"
                    f"  echo '===FIM==='\n"
                    f"fi\n"
                )
                self._sock.sendall(payload.encode("utf-8"))

                buf = b""
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        chunk = self._sock.recv(8192)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    if b"===FIM===" in buf:
                        break

                text = buf.decode("utf-8", errors="replace")

                if "===COMPILE_FAILED===" in text:
                    err_raw = text.split("===COMPILE_FAILED===", 1)[1].split("===FIM===")[0]
                    return SandboxResult(False, "", self._clean_output(err_raw), 1)

                if "===EXECUTANDO===" in text and "===FIM===" in text:
                    exec_part = text.split("===EXECUTANDO===", 1)[1].split("===FIM===")[0]
                    rc_match = re.search(r"APP_RC=(\d+)", exec_part)
                    rc = int(rc_match.group(1)) if rc_match else 0
                    # Remove o marcador APP_RC=...
                    clean_stdout = re.sub(r"APP_RC=\d+\r?\n?", "", exec_part)
                    return SandboxResult(
                        success=(rc == 0),
                        stdout=self._clean_output(clean_stdout),
                        stderr="",
                        exit_code=rc,
                    )

                return SandboxResult(False, text[-1000:], "Timeout ou execução incompleta", -1)
            except Exception as e:
                self._sock = None
                self.log.exception("_run_c: erro")
                return SandboxResult(False, "", f"Erro socket: {e}", -1)

    def _run_python(self, code: str, args: Optional[list[str]],
                    timeout: int) -> SandboxResult:
        if not self._ensure_socket():
            return SandboxResult(False, "", "Daemon offline ou socket morto", -2)

        args = args or []
        import shlex
        args_str = " ".join(shlex.quote(a) for a in args)
        eof = f"EOF_{int(time.time()*1000)}"

        with self._lock:
            try:
                self._drain(self._sock, wait=0.05)
                run_timeout = max(5, timeout - 5)
                payload = (
                    f"killall -9 python3 2>/dev/null\n"
                    f"cat << '{eof}' > /tmp/main.py\n"
                    f"{code}\n"
                    f"{eof}\n"
                    f"rm -f /tmp/out.txt /tmp/err.txt\n"
                    f"echo '===EXECUTANDO==='\n"
                    f"timeout -s 9 {run_timeout} python3 /tmp/main.py {args_str} > /tmp/out.txt 2> /tmp/err.txt\n"
                    f"PY_RC=$?\n"
                    f"if [ $PY_RC -eq 137 ] || [ $PY_RC -eq 124 ]; then\n"
                    f"  echo 'Erro: Execução excedeu o tempo limite (possivel loop infinito ou input bloqueante).' >> /tmp/err.txt\n"
                    f"fi\n"
                    f"echo \"PY_RC=$PY_RC\"\n"
                    f"echo '===STDOUT==='\n"
                    f"cat /tmp/out.txt\n"
                    f"echo '===STDERR==='\n"
                    f"cat /tmp/err.txt\n"
                    f"echo '===FIM==='\n"
                )
                self._sock.sendall(payload.encode("utf-8"))

                buf = b""
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        chunk = self._sock.recv(8192)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    if b"===FIM===" in buf:
                        break

                text = buf.decode("utf-8", errors="replace")
                if "===STDOUT===" in text and "===FIM===" in text:
                    out_raw = text.split("===STDOUT===", 1)[1].split("===STDERR===")[0]
                    err_raw = text.split("===STDERR===", 1)[1].split("===FIM===")[0]
                    rc_match = re.search(r"PY_RC=(\d+)", text)
                    rc = int(rc_match.group(1)) if rc_match else 0
                    return SandboxResult(
                        success=(rc == 0),
                        stdout=self._clean_output(out_raw),
                        stderr=self._clean_output(err_raw),
                        exit_code=rc,
                    )

                return SandboxResult(False, text[-1000:], "Timeout ou execução incompleta", -1)
            except Exception as e:
                self._sock = None
                self.log.exception("_run_python: erro")
                return SandboxResult(False, "", f"Erro socket: {e}", -1)


