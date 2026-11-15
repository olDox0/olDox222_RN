# -*- coding: utf-8 -*-
"""QemuSandbox — Executa código C compilado em um Alpine Linux isolado."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import re
import threading
import queue
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int

class QemuSandbox:
    def __init__(self, alpine_root: str | Path = "data/sandbox/alpine") -> None:
        self.alpine_root = Path(alpine_root)
        self.qemu_exe = self._find_qemu()

    @staticmethod
    def _find_qemu() -> str:
        found = shutil.which("qemu-system-x86_64")
        if found:
            return found
        candidates = [
            r"C:\Program Files\qemu\qemu-system-x86_64.exe",
            r"C:\Program Files (x86)\qemu\qemu-system-x86_64.exe",
            r"C:\qemu\qemu-system-x86_64.exe",
            str(Path.home() / "qemu" / "qemu-system-x86_64.exe"),
            str(Path.cwd() / ".doxoade" / "opt" / "qemu" / "qemu-system-x86_64.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return ""

    def is_available(self) -> bool:
        return bool(self.qemu_exe and os.path.exists(self.qemu_exe))

    def install(self, version: str = "v3.21") -> bool:
        base_url = f"https://dl-cdn.alpinelinux.org/alpine/{version}/releases/x86_64/"
        try:
            with urllib.request.urlopen(base_url, timeout=30) as resp:
                html = resp.read().decode("utf-8")
        except Exception as e:
            print(f"  [ERRO] Falha ao acessar o índice do Alpine: {e}")
            return False

        matches = re.findall(r'netboot-(\d+\.\d+\.\d+)/', html)
        if not matches:
            print("  [ERRO] Nenhum diretório netboot encontrado.")
            return False

        latest = max(matches, key=lambda v: tuple(map(int, v.split("."))))
        netboot_dir = f"netboot-{latest}/"
        print(f"  [OK] Versão mais recente encontrada: {latest}")

        files = ["vmlinuz-virt", "initramfs-virt", "modloop-virt"]
        self.alpine_root.mkdir(parents=True, exist_ok=True)

        for fname in files:
            dest = self.alpine_root / fname
            if dest.exists():
                print(f"  [OK] {fname} já existe ({dest.stat().st_size // 1024} KB)")
                continue
            url = base_url + netboot_dir + fname
            print(f"  [..] Baixando {fname}...")
            try:
                with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
                print(f"  [OK] {fname} salvo ({dest.stat().st_size // 1024} KB)")
            except Exception as e:
                print(f"  [ERRO] Falha ao baixar {fname}: {e}")
                return False
        return True

    def _abs(self, p: Path) -> str:
        """Retorna caminho absoluto com barras normais (QEMU aceita / no Windows)."""
        return str(Path(p).resolve()).replace("\\", "/")

    def run_c_code(self, code: str, args: list[str] | None = None, timeout: int = 120) -> SandboxResult:
        if not self.is_available():
            return SandboxResult(False, "", "QEMU não encontrado.", -2)
        if not (self.alpine_root / "vmlinuz-virt").exists():
            return SandboxResult(False, "", "Arquivos do Alpine ausentes. Rode 'orn sandbox install'.", -2)

        args = args or []
        tmp_dir = Path(tempfile.mkdtemp(prefix="orn_qemu_")).resolve()

        try:
            (tmp_dir / "main.c").write_text(code, encoding="utf-8")
            # Script com sentinelas claros para o parser
            script = """#!/bin/sh
echo "===COMPILANDO==="
apk add gcc musl-dev > /dev/null 2>&1 || echo "AVISO: falha ao instalar gcc"
gcc main.c -o app 2>&1
echo "===EXECUTANDO==="
./app "$@"
echo "===FIM==="
"""
            (tmp_dir / "run.sh").write_text(script, encoding="utf-8")

            kernel_abs  = str((self.alpine_root / "vmlinuz-virt").resolve()).replace("\\", "/")
            initrd_abs  = str((self.alpine_root / "initramfs-virt").resolve()).replace("\\", "/")
            tmp_dir_abs = str(tmp_dir).replace("\\", "/")

            cmd = [
                self.qemu_exe,
                "-m", "256M",
                "-nographic",
                "-kernel", kernel_abs,
                "-initrd", initrd_abs,
                # Sem "modloop=" -- o OpenRC tenta de qualquer forma mas falha suave
                "-append", "console=ttyS0 alpine_repo=https://dl-cdn.alpinelinux.org/alpine/v3.21/main ip=dhcp",
                "-drive", f"file=fat:rw:{tmp_dir_abs},format=raw,media=disk",
                "-net", "nic", "-net", "user",
                "-no-reboot"
            ]

            qemu_dir = os.path.dirname(self.qemu_exe) if self.qemu_exe else None
            process = subprocess.Popen(
                cmd, cwd=qemu_dir,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )

            q = queue.Queue()
            def _reader():
                for line in process.stdout:
                    q.put(line)
            threading.Thread(target=_reader, daemon=True).start()

            # Fase 1: aguardar boot -- detecta "Welcome to Alpine" ou prompt de login
            output_lines: list[str] = []
            booted = False
            boot_deadline = time.time() + 180  # 3 min: Alpine + apk demora no Celeron
            while time.time() < boot_deadline:
                try:
                    line = q.get(timeout=1.0)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                output_lines.append(line)
                low = line.lower()
                if ("welcome to alpine" in low or
                    "starting firstboot" in low or
                    "login:" in low or
                    "~#" in line or
                    "localhost:~" in line):
                    booted = True
                    break

            if not booted:
                process.kill()
                return SandboxResult(False, "".join(output_lines),
                                     "Timeout no boot do QEMU (3 min)", -1)

            # Fase 2: enviar login (se necessário) + script
            # O getty do Alpine aceita "root" sem senha no primeiro boot
            time.sleep(1)
            process.stdin.write("root\n")
            process.stdin.flush()
            time.sleep(2)

            # Monta o FAT e roda o script
            args_str = " ".join(args)
            process.stdin.write("mkdir -p /mnt && mount -t vfat /dev/sda /mnt\n")
            process.stdin.write(f"cd /mnt && sh run.sh {args_str}\n")
            process.stdin.flush()

            # Fase 3: aguardar a execução terminar
            exec_deadline = time.time() + timeout
            while time.time() < exec_deadline:
                try:
                    line = q.get(timeout=1.0)
                except queue.Empty:
                    continue
                output_lines.append(line)
                if "===FIM===" in line:
                    break

            process.kill()
            full_output = "".join(output_lines)

            # Parse com as novas sentinelas
            if "===EXECUTANDO===" in full_output:
                stdout_clean = full_output.split("===EXECUTANDO===")[1].split("===FIM===")[0].strip()
                stderr_clean = ""
                if "===COMPILANDO===" in full_output:
                    stderr_clean = full_output.split("===COMPILANDO===")[1].split("===EXECUTANDO===")[0].strip()
                # Remove ruído do console (linhas começando com [ )
                stdout_clean = "\n".join(
                    l for l in stdout_clean.splitlines() if not l.strip().startswith("[")
                ).strip()
                return SandboxResult(True, stdout_clean, stderr_clean, 0)
            else:
                return SandboxResult(False, full_output,
                                     "Execução incompleta (sem ===FIM===)", -1)

        except Exception as e:
            return SandboxResult(False, "", f"Erro fatal no QEMU: {e}", -1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
