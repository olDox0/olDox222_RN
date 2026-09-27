# -*- coding: utf-8 -*-
"""Helpers para configuração de afinidade de CPU (processo atual)."""

from __future__ import annotations

import os
from typing import Iterable


def _parse_cpuset(cpuset: str) -> set[int]:
    result: set[int] = set()
    for chunk in cpuset.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a.strip(), 10)
            end = int(b.strip(), 10)
            if end < start:
                start, end = end, start
            for cpu in range(start, end + 1):
                if cpu >= 0:
                    result.add(cpu)
            continue
        cpu = int(part, 10)
        if cpu >= 0:
            result.add(cpu)
    return result


def _mask_from_cpus(cpus: Iterable[int]) -> int:
    mask = 0
    for cpu in cpus:
        if cpu >= 0:
            mask |= 1 << cpu
    return mask


def cpus_from_options(cpu_mask: str | None, cpuset: str | None) -> set[int]:
    if cpuset:
        return _parse_cpuset(cpuset)
    if not cpu_mask:
        return set()
    value = int(cpu_mask, 0)
    cpus: set[int] = set()
    bit = 0
    while value:
        if value & 1:
            cpus.add(bit)
        value >>= 1
        bit += 1
    return cpus


def apply_process_affinity(cpu_mask: str | None, cpuset: str | None) -> tuple[bool, str]:
    """Aplica afinidade no processo atual.

    Prioridade: cpuset > cpu_mask.
    Retorna (aplicado, detalhe).
    """
    cpus = cpus_from_options(cpu_mask, cpuset)
    if not cpus:
        return False, "sem afinidade (cpu_mask/cpuset vazio)"

    cpu_count = os.cpu_count() or 0
    if cpu_count > 0:
        cpus = {c for c in cpus if c < cpu_count}
    if not cpus:
        return False, "afinidade vazia apos filtro por CPUs disponiveis"

    # Linux/Unix
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, cpus)
        return True, f"cpuset={sorted(cpus)}"

    # Windows
    if os.name == "nt":
        import ctypes

        mask = _mask_from_cpus(cpus)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.kernel32.SetProcessAffinityMask(handle, ctypes.c_size_t(mask))
        if not ok:
            raise OSError("SetProcessAffinityMask falhou")
        return True, f"mask=0x{mask:X} (cpus={sorted(cpus)})"

    return False, "plataforma sem suporte para afinidade"
