# -*- coding: utf-8 -*-
"""QemuDaemon — Alpine QEMU persistente com observabilidade total.

Três fontes de evidência em paralelo:
  serial.log      → capturado pelo próprio QEMU (chardev logfile)
  qemu_trace.log  → eventos do emulador (-d int,guest_errors,cpu_reset)
  daemon.log      → ações do Python (handshake, sockets)
"""
from __future__ import annotations

import logging
import os
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

    def _port_responds(self, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((HOST, port), timeout=timeout):
                return True
        except OSError:
            return False

    def status(self) -> DaemonStatus:
        pid = self._read_pid()
        alive = pid is not None and self._pid_alive(pid)
        port = self._read_port()
        resp = port is not None and self._port_responds(port)
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
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
            self._clean_state()
            self._kill_stale_qemu()
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
        if not (self.alpine_root / "vmlinuz-virt").exists():
            self.log.error("_try_boot: alpine ausente")
            return False

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        for f in (SERIAL_FILE, TRACE_FILE):
            f.unlink(missing_ok=True)

        kernel = str(self.alpine_root / "vmlinuz-virt")
        initrd = str(self.alpine_root / "initramfs-virt")
        modloop = str(self.alpine_root / "modloop-virt")

        # ── VOTA AO dl-cdn (linorg.usp.br está 404) ──
        cmd = [
            self.qs.qemu_exe, "-m", "512M",
            "-kernel", kernel, "-initrd", initrd,
            "-append",
            "console=ttyS0,115200 ip=dhcp "
            "alpine_repo=http://dl-cdn.alpinelinux.org/alpine/v3.21/main "
            "modloop=/dev/vda "
            "rootflags=size=400M",
            "-chardev",
            f"socket,id=serial0,host={HOST},port={port},server=on,wait=off,"
            f"logfile={str(SERIAL_FILE.resolve()).replace(chr(92), '/')},logappend=off",
            "-serial", "chardev:serial0",
            "-drive", f"file={modloop},if=virtio,format=raw,readonly=on",
            # Disco persistente: mesma sintaxe do modloop (funciona)
            *(["-drive",
               f"file={str(DISK_FILE.resolve()).replace(chr(92), '/')},"
               f"if=virtio,format=qcow2"]
              if DISK_FILE.exists() else []),
            "-D", str(TRACE_FILE.resolve()),
            "-d", "guest_errors,cpu_reset",
            "-monitor", "none",
            "-display", "none",
            "-net", "nic", "-net", "user",
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
        if self._sock is not None:
            print(f"    [OK] Socket logado.")
        else:
            print(f"    [!] Boot OK, mas socket falhou.")
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
        """Handshake com drenagem agressiva e timeouts curtos."""
        try:
            s = socket.create_connection((HOST, port), timeout=5.0)
        except OSError as exc:
            self.log.error("open_serial: connect falhou: %s", exc)
            return None
        self.log.debug("open_serial: TCP conectado em %s:%d", HOST, port)

        # 1. DRENAGEM AGRESSIVA — descarta o buffer acumulado
        s.settimeout(0.15)
        drained = b""
        for _ in range(80):  # até 12s drenando
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                drained += chunk
            except socket.timeout:
                break
        if drained:
            self.log.debug("open_serial: drenou %d bytes", len(drained))

        # 2. Envia Enter para "acordar" o prompt
        try:
            s.sendall(b"\n")
            time.sleep(0.4)
        except OSError:
            pass

        # 3. Aguarda prompt com timeout curto
        s.settimeout(1.5)
        deadline = time.time() + timeout
        got_prompt = False
        buffer = b""

        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                # Se já viu login mas não ~#, tenta root
                if b"login:" in buffer.lower() and b"~#" not in buffer:
                    try:
                        s.sendall(b"root\n")
                    except OSError:
                        break
                else:
                    try:
                        s.sendall(b"\n")
                    except OSError:
                        break
                continue
            if not chunk:
                break
            buffer += chunk
            if b"~#" in buffer or b"# " in buffer[-10:]:
                got_prompt = True
                break
            if b"login:" in buffer.lower():
                try:
                    s.sendall(b"root\n")
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

        # 4. Desativa echo (opcional, sem esperar resposta)
        try:
            s.sendall(b"stty -echo 2>/dev/null\n")
            time.sleep(0.2)
        except OSError:
            pass

        # 5. Marker de confirmação (rápido)
        marker = f"OK_{int(time.time()*1000)}"
        try:
            s.sendall(f"echo {marker}\n".encode())
            s.settimeout(2.0)
            wait_buf = b""
            while marker.encode() not in wait_buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                wait_buf += chunk
            if marker.encode() not in wait_buf:
                self.log.warning("open_serial: marker não voltou")
                # Mesmo assim retorna — o socket pode servir
        except OSError:
            pass

        s.settimeout(0.5)
        return s

    def _ensure_socket(self) -> bool:
        if self._sock is not None:
            try:
                self._sock.settimeout(0.3)
                try:
                    self._sock.sendall(b"echo __ALIVE__\n")
                    self._drain(self._sock, wait=0.3)
                except OSError:
                    pass
                return True
            except Exception:
                try:
                    self._sock.close()
                except Exception:
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
        import re
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
                        if re.search(r"[a-z][a-z0-9\-]*:~\s*#", text):
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
        self._kill_stale_qemu()
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
                self._drain(self._sock, wait=0.2)
                marker = f"M_{int(time.time()*1000)}"
                # \n em vez de && — funciona mesmo se cmd termina com ';', '}', 'fi'
                self._sock.sendall(f"{cmd}\necho {marker}\n".encode())
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
                    if marker.encode() in buf:
                        break
                text = buf.decode("utf-8", errors="replace")
                cleaned = []
                for l in text.splitlines():
                    s = l.strip()
                    if not s:
                        continue
                    if s == cmd.strip() or s == f"echo {marker}" or s == marker:
                        continue
                    if "localhost:~#" in s:
                        s = s.split("localhost:~#", 1)[-1].strip()
                        if not s:
                            continue
                    cleaned.append(s)
                return "\n".join(cleaned)
            except Exception as exc:
                self._sock = None
                return f"(erro: {exc})"

    def bootstrap(self) -> bool:
        if not self._ensure_socket():
            self.log.error("bootstrap: sem socket")
            print("  [ERRO] socket fechado. Reinicie o daemon.")
            return False

        # ── 1. Config repos no tmpfs ──
        print("  [..] Configurando repos no tmpfs...")
        self.shell(
            "echo 'http://dl-cdn.alpinelinux.org/alpine/v3.21/main' > /etc/apk/repositories",
            timeout=10,
        )
        self.shell(
            "echo 'http://dl-cdn.alpinelinux.org/alpine/v3.21/community' >> /etc/apk/repositories",
            timeout=10,
        )

        # ── 2. Instala e2fsprogs no tmpfs ──
        has_mkfs = self.shell("which mkfs.ext2 >/dev/null 2>&1 && echo Y || echo N", timeout=10)
        if "Y" not in has_mkfs:
            print("  [..] Instalando e2fsprogs (mkfs.ext2)...")
            for attempt in range(3):
                r = self.shell("apk add --no-cache e2fsprogs 2>&1 | tail -4", timeout=120)
                if "OK:" in r and "MiB in" in r:
                    print(f"  [OK] e2fsprogs instalado (tentativa {attempt+1})")
                    break
                print(f"  [!]  falhou retry {attempt+1}/3")
                time.sleep(2)
            else:
                print("  [ERRO] e2fsprogs falhou.")
                return False

        # ── 3. Diagnóstico + monta /dev/vdb em /mnt/persist ──
        persist_ok = False
        if DISK_FILE.exists():
            print("  [..] Diagnóstico de dispositivos...")
            for cmd in ["ls /dev/vd*", "cat /proc/partitions"]:
                r = self.shell(cmd + " 2>&1", timeout=10)
                print(f"      $ {cmd}")
                for line in r.splitlines()[:6]:
                    if line.strip() and not line.strip().startswith("M_"):
                        print(f"        {line[:120]}")

            print("  [..] Montando /dev/vdb em /mnt/persist...")
            self.shell("mkdir -p /mnt/persist", timeout=10)
            r = self.shell("test -b /dev/vdb && echo VDB_OK || echo VDB_NO", timeout=10)
            if "VDB_NO" in r:
                print("  [!]  /dev/vdb NÃO existe — QEMU não anexou o disco")
                print("  [..] Continuando com tmpfs (sem persistência)")
            else:
                print("  [OK] /dev/vdb detectado")
                # 3a. Carrega módulos do kernel (ext4, ext2)
                print("  [..] Carregando módulos do kernel (ext4)...")
                self.shell("modprobe ext4 2>&1; modprobe ext2 2>&1; modprobe ext2 2>&1; echo MODPROBE_DONE", timeout=15)
                r = self.shell("cat /proc/filesystems | grep -E 'ext[234]' || echo NO_EXT", timeout=10)
                if "NO_EXT" in r:
                    print("  [!]  ext4 não disponível no kernel — usando FAT32")
                else:
                    print(f"  [OK] {r.strip().splitlines()[0][:80]}")

                # 3b. Tenta mount ext4/ext2 (com modprobe feito)
                for fstype in ["ext4", "ext2"]:
                    r = self.shell(
                        f"mount -t {fstype} /dev/vdb /mnt/persist 2>&1; "
                        f"mountpoint -q /mnt/persist && echo M_OK || echo M_NO",
                        timeout=15,
                    )
                    if "M_OK" in r:
                        persist_ok = True
                        print(f"  [OK] /mnt/persist montado ({fstype})")
                        break
                    else:
                        # Captura erro real do mount
                        err_line = [l for l in r.splitlines() if l.strip() and "M_NO" not in l and "M_" not in l]
                        if err_line:
                            print(f"  [!]  mount {fstype}: {err_line[0][:150]}")

                # 3c. Se não montou, formata com mke2fs (já funciona)
                if not persist_ok:
                    print("  [..] Formatando /dev/vdb como ext4...")
                    mk = self.shell(
                        "mke2fs -t ext4 -F /dev/vdb 2>&1 | tail -3; echo RC=$?",
                        timeout=120,
                    )
                    print(f"  [..] mke2fs: {mk.strip()[-300:]}")
                    for fstype in ["ext4", "ext2"]:
                        r = self.shell(
                            f"mount -t {fstype} /dev/vdb /mnt/persist 2>&1; "
                            f"mountpoint -q /mnt/persist && echo M_OK || echo M_NO",
                            timeout=15,
                        )
                        if "M_OK" in r:
                            persist_ok = True
                            print(f"  [OK] /mnt/persist montado ({fstype})")
                            break
                        else:
                            err_line = [l for l in r.splitlines() if l.strip() and "M_NO" not in l and "M_" not in l]
                            if err_line:
                                print(f"  [!]  mount {fstype}: {err_line[0][:150]}")

                # 3d. Fallback: FAT32 (sempre funciona, mas sem symlinks)
                if not persist_ok:
                    print("  [..] Fallback: formatando como FAT32...")
                    self.shell("mkfs.vfat -F 32 /dev/vdb 2>&1 | tail -2; echo RC=$?", timeout=60)
                    r = self.shell(
                        "mount -t vfat /dev/vdb /mnt/persist 2>&1; "
                        "mountpoint -q /mnt/persist && echo M_OK || echo M_NO",
                        timeout=15,
                    )
                    if "M_OK" in r:
                        persist_ok = True
                        print("  [OK] /mnt/persist montado (vfat) — sem symlinks")
                    else:
                        err_line = [l for l in r.splitlines() if l.strip() and "M_NO" not in l and "M_" not in l]
                        if err_line:
                            print(f"  [!]  mount vfat: {err_line[0][:150]}")

                if not persist_ok:
                    print("  [!]  Nenhum fs funcionou. Diagnóstico final:")
                    r = self.shell("cat /proc/filesystems | head -20", timeout=10)
                    for line in r.splitlines()[:20]:
                        print(f"      {line[:120]}")
                    print("  [..] Continuando com tmpfs (sem persistência)")

        # ── 4. Early-return se já bootstrapped ──
        if persist_ok:
            check = self.shell("test -f /persist/.orn_ready && echo Y || echo N", timeout=10)
            if "Y" in check:
                print("  [OK] Bootstrap em cache (/persist/.orn_ready existe).")
                self.shell("touch /root/.orn_ready", timeout=5)
                return True

        # ── 5. Prepara estrutura em /persist (cada mkdir separado) ──
        if persist_ok:
            print("  [..] Criando estrutura em /persist...")
            for d in ["etc/apk/keys", "lib/apk/db", "var/cache/apk"]:
                path = f"/persist/{d}"
                self.shell(f"mkdir -p {path}", timeout=10)
            # Diagnóstico
            r = self.shell("ls -la /persist/ 2>&1", timeout=10)
            print(f"  [..] ls /persist/:")
            for line in r.splitlines()[:8]:
                print(f"      {line}")

            # Copia keys do tmpfs
            print("  [..] Copiando keys do tmpfs...")
            self.shell("cp -a /etc/apk/keys/* /persist/etc/apk/keys/ 2>/dev/null || true", timeout=10)
            r = self.shell("ls /persist/etc/apk/keys/ 2>&1 | wc -l", timeout=10)
            n_keys = r.strip().splitlines()[-1] if r else "?"
            print(f"  [..] keys copiadas: {n_keys}")

            # Copia DB installed do tmpfs
            print("  [..] Copiando DB apk do tmpfs...")
            self.shell("cp -a /lib/apk/db/* /persist/lib/apk/db/ 2>/dev/null || true", timeout=10)
            r = self.shell("ls /persist/lib/apk/db/ 2>&1 | wc -l", timeout=10)
            n_db = r.strip().splitlines()[-1] if r else "?"
            print(f"  [..] DB arquivos: {n_db}")

            # Repos do persist
            self.shell(
                "echo 'http://dl-cdn.alpinelinux.org/alpine/v3.21/main' > /persist/etc/apk/repositories",
                timeout=10,
            )
            self.shell(
                "echo 'http://dl-cdn.alpinelinux.org/alpine/v3.21/community' >> /persist/etc/apk/repositories",
                timeout=10,
            )

        # ── 6. apk add ──
        print(f"  [..] apk add (root={'/persist' if persist_ok else '/'})...")
        if persist_ok:
            # Usa keys e repos do TMPFS, root = /persist (onde instalar)
            apk_add_cmd = (
                "apk --root /persist "
                "--keys-dir /etc/apk/keys "
                "--repositories-file /etc/apk/repositories "
                "--no-cache add gcc musl-dev python3 py3-pip 2>&1 | tail -20"
            )
        else:
            apk_add_cmd = "apk add --no-cache gcc musl-dev python3 py3-pip 2>&1 | tail -15"

        add_ok = False
        last_out = ""
        for attempt in range(3):
            last_out = self.shell(apk_add_cmd, timeout=600)
            if "OK:" in last_out and "MiB in" in last_out:
                add_ok = True
                print(f"  [OK] apk add (tentativa {attempt+1}/3)")
                print(last_out[-400:])
                break
            print(f"  [!]  falhou (tentativa {attempt+1}/3):")
            for line in last_out.splitlines()[-8:]:
                print(f"      | {line[:150]}")
            time.sleep(3)

        if not add_ok:
            print(f"  [ERRO] apk add falhou 3x. Saída completa:")
            print(last_out[-1500:])
            return False

        # ── 7. Flags de conclusão ──
        if persist_ok:
            self.shell("touch /persist/.orn_ready", timeout=5)
            print("  [OK] Bootstrap persistente concluído (/persist/.orn_ready).")
        self.shell("touch /root/.orn_ready", timeout=5)
        print("  [OK] Bootstrap concluído.")
        return True

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
        probe = self.shell("test -f /root/.orn_ready && echo Y || echo N", timeout=10)
        if "Y" not in probe:
            return SandboxResult(False, "",
                "Bootstrap não executado. Rode 'orn sandbox bootstrap' primeiro.", -2)

        args = args or []
        args_str = " ".join(args)
        eof = f"EOF_{int(time.time()*1000)}"

        with self._lock:
            try:
                self._drain(self._sock, wait=0.2)

                self._sock.sendall(f"cat > /tmp/main.c << '{eof}'\n".encode())
                for line in code.splitlines():
                    self._sock.sendall((line + "\n").encode())
                    time.sleep(0.005)
                self._sock.sendall(f"{eof}\n".encode())
                time.sleep(0.3)

                self._sock.sendall(b"rm -f /tmp/app\n")
                self._sock.sendall(b"echo '===COMPILANDO==='\n")
                self._sock.sendall(b"gcc /tmp/main.c -o /tmp/app 2>&1\n")
                self._sock.sendall(b"GCC_RC=$?\n")
                self._sock.sendall(
                    b"if [ $GCC_RC -ne 0 ]; then echo '===COMPILE_FAILED==='; "
                    b"else echo '===COMPILADO_OK==='; fi\n"
                )
                time.sleep(0.3)

                self._sock.sendall(b"if [ -x /tmp/app ]; then\n")
                self._sock.sendall(b"echo '===EXECUTANDO==='\n")
                self._sock.sendall(f"/tmp/app {args_str} 2>&1\n".encode())
                self._sock.sendall(b"echo '===FIM==='\n")
                self._sock.sendall(b"fi\n")

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
                    if b"===FIM===" in buf or b"===COMPILE_FAILED===" in buf:
                        break

                text = buf.decode("utf-8", errors="replace")

                if "===COMPILE_FAILED===" in text:
                    stderr_raw = text.split("===COMPILE_FAILED===")[0]
                    if "===COMPILANDO===" in stderr_raw:
                        stderr_raw = stderr_raw.split("===COMPILANDO===", 1)[1]
                    return SandboxResult(False, "", self._clean_output(stderr_raw), 1)

                if "===EXECUTANDO===" in text and "===FIM===" in text:
                    stdout_raw = text.split("===EXECUTANDO===", 1)[1].split("===FIM===")[0]
                    stderr_raw = ""
                    if "===COMPILANDO===" in text:
                        stderr_raw = text.split("===COMPILANDO===", 1)[1].split("===COMPILADO_OK===")[0]
                    return SandboxResult(
                        True,
                        self._clean_output(stdout_raw),
                        self._clean_output(stderr_raw),
                        0,
                    )

                return SandboxResult(False, text[-2000:], "Sem marcador de fim", -1)

            except Exception as e:
                self._sock = None
                self.log.exception("_run_c: erro")
                return SandboxResult(False, "", f"Erro socket: {e}", -1)

    def _run_python(self, code: str, args: Optional[list[str]],
                    timeout: int) -> SandboxResult:
        if not self._ensure_socket():
            return SandboxResult(False, "", "Daemon offline ou socket morto", -2)

        py_check = self.shell(
            "which python3 >/dev/null 2>&1 && python3 --version 2>&1 || echo NO_PY",
            timeout=10,
        )
        if "NO_PY" in py_check or "Python 3" not in py_check:
            return SandboxResult(False, "",
                "python3 ausente no Alpine. Rode 'orn sandbox bootstrap'.", -2)

        args = args or []
        import shlex as _shlex
        args_str = " ".join(_shlex.quote(a) for a in args)
        eof = f"EOF_{int(time.time()*1000)}"

        with self._lock:
            try:
                self._drain(self._sock, wait=0.2)

                self._sock.sendall(f"cat > /tmp/main.py << '{eof}'\n".encode())
                for line in code.splitlines():
                    self._sock.sendall((line + "\n").encode())
                    time.sleep(0.005)
                self._sock.sendall(f"{eof}\n".encode())
                time.sleep(0.3)

                self._sock.sendall(b"rm -f /tmp/out.txt /tmp/err.txt\n")
                self._sock.sendall(b"echo '===EXECUTANDO==='\n")
                self._sock.sendall(
                    f"python3 /tmp/main.py {args_str} > /tmp/out.txt 2> /tmp/err.txt\n".encode()
                )
                self._sock.sendall(b"PY_RC=$?\n")
                self._sock.sendall(b"echo \"PY_RC=$PY_RC\"\n")
                self._sock.sendall(b"echo '===STDOUT==='\n")
                self._sock.sendall(b"cat /tmp/out.txt\n")
                self._sock.sendall(b"echo '===STDERR==='\n")
                self._sock.sendall(b"cat /tmp/err.txt\n")
                self._sock.sendall(b"echo '===FIM==='\n")

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
                    err_raw = ""
                    if "===STDERR===" in text:
                        err_raw = text.split("===STDERR===", 1)[1].split("===FIM===")[0]

                    import re as _re
                    rc_match = _re.search(r"PY_RC=(\d+)", text)
                    rc = int(rc_match.group(1)) if rc_match else 0

                    return SandboxResult(
                        success=(rc == 0),
                        stdout=self._clean_output(out_raw),
                        stderr=self._clean_output(err_raw),
                        exit_code=rc,
                    )

                return SandboxResult(False, text[-2000:], "Sem marcador de fim", -1)

            except Exception as e:
                self._sock = None
                self.log.exception("_run_python: erro")
                return SandboxResult(False, "", f"Erro socket: {e}", -1)

