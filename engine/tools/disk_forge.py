# -*- coding: utf-8 -*-
"""DiskForge — cria e gerencia a imagem de disco persistente do sandbox.

Usa qcow2 (espalhado, ocupa ~200KB em disco até ser escrito).
O guest formata como ext2 no primeiro bootstrap.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class DiskForge:
    @staticmethod
    def _qemu_img() -> str | None:
        """Localiza qemu-img.exe na mesma pasta do qemu-system."""
        from engine.tools.qemu_sandbox import QemuSandbox
        qs = QemuSandbox()
        if not qs.qemu_exe:
            return None
        candidate = Path(qs.qemu_exe).parent / "qemu-img.exe"
        return str(candidate) if candidate.exists() else None

    @classmethod
    def forge_qcow2(cls, path: str | Path, size_mb: int = 512) -> Path:
        """Cria alpine.img.qcow2 (disco vazio, formato qcow2)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            return p

        qemu_img = cls._qemu_img()
        if qemu_img is None:
            raise FileNotFoundError(
                "qemu-img.exe não encontrado. Reinstale o QEMU para Windows."
            )

        print(f"  [..] Criando {p.name} ({size_mb} MB, qcow2)...")
        res = subprocess.run(
            [qemu_img, "create", "-f", "qcow2", str(p), f"{size_mb}M"],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            raise RuntimeError(f"qemu-img create falhou: {res.stderr.strip()}")
        print(f"  [OK] {p.name} criado ({p.stat().st_size} bytes em disco)")
        return p

    @staticmethod
    def wipe(path: str | Path) -> bool:
        """Remove a imagem (reset do sandbox)."""
        p = Path(path)
        if p.exists():
            p.unlink()
            return True
        return False

    @staticmethod
    def exists(path: str | Path) -> bool:
        return Path(path).exists()
