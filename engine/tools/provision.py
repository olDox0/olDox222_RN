# -*- coding: utf-8 -*-
# engine/tools/provision.py
"""
Provisionamento de ferramentas nativas do llama.cpp.

Compila `llama-quantize` (e opcionalmente outros targets) a partir do
`thirdparty/llama.cpp`, num diretório isolado (`build_tools/`) para não
tocar em `build/` nem `build_finetune/`.

Feedback ao vivo: o output do cmake é impresso em tempo real.

God: Hefesto (forja) + Hermes (descoberta).
OSL-15: falha de build vira ProvisionResult(success=False), nunca exceção.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LLAMA_SRC    = _PROJECT_ROOT / "thirdparty" / "llama.cpp"
_BUILD_DIR    = _LLAMA_SRC / "build_tools"
_BIN_DIR      = _BUILD_DIR / "bin"
_NATIVE_DIR   = _PROJECT_ROOT / "native"

_TARGETS = {
    "llama-quantize": True,
    "llama-cli":      True,
    "llama-gguf":     True,
}


@dataclass
class ProvisionResult:
    tool:      str
    found:     bool
    path:      Path | None = None
    built:     bool = False
    elapsed_s: float = 0.0
    error:     str | None = None


def detect_profile() -> str:
    env = os.environ.get("ORN_PROFILE", "").strip().lower()
    if env in {"1235u", "portable"}:
        return env
    if platform.machine().lower() in ("amd64", "x86_64"):
        return "1235u"
    return "portable"


def _cmake_args(profile: str) -> list[str]:
    args = [
        "-G", "MinGW Makefiles",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DLLAMA_CURL=OFF",
        "-DLLAMA_BUILD_TESTS=OFF",
        "-DLLAMA_BUILD_EXAMPLES=OFF",
        "-DLLAMA_BUILD_SERVER=OFF",
    ]
    if profile == "portable":
        args += [
            "-DGGML_NATIVE=OFF",
            "-DGGML_AVX=OFF",
            "-DGGML_AVX2=OFF",
            "-DGGML_FMA=OFF",
            "-DGGML_F16C=OFF",
            "-DGGML_SSE42=ON",
        ]
    else:
        args += ["-DGGML_NATIVE=ON"]
    return args


def find_tool(tool: str) -> Path | None:
    exe = f"{tool}.exe" if os.name == "nt" else tool
    for c in (_BIN_DIR / exe, _NATIVE_DIR / exe):
        if c.exists():
            return c
    which = shutil.which(tool)
    return Path(which) if which else None


def check_all() -> dict[str, Path | None]:
    return {name: find_tool(name) for name in _TARGETS}


def _run_live(cmd: list[str], cwd: Path, timeout: int = 600) -> tuple[int, str]:
    """Executa com output ao vivo e retorna (returncode, tail)."""
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1,
        )
    except (OSError, FileNotFoundError) as exc:
        return -1, str(exc)

    tail: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            print(f"  | {line}", flush=True)
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)
    except KeyboardInterrupt:
        proc.terminate()
        return -1, "interrompido pelo usuário (Ctrl+C)"

    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, f"[timeout {timeout}s]"

    return rc, "\n".join(tail)


def build_tool(tool: str, profile: str = "auto") -> ProvisionResult:
    t0 = time.monotonic()

    existing = find_tool(tool)
    if existing is not None:
        return ProvisionResult(
            tool=tool, found=True, path=existing,
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if not _LLAMA_SRC.exists():
        return ProvisionResult(
            tool=tool, found=False,
            error=f"fonte não encontrada: {_LLAMA_SRC}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    if profile == "auto":
        profile = detect_profile()

    # 1. configure (idempotente)
    cache = _BUILD_DIR / "CMakeCache.txt"
    if not cache.exists():
        print(f"  [1/2] cmake configure (perfil={profile})...", flush=True)
        rc, tail = _run_live(
            ["cmake", "-B", str(_BUILD_DIR)] + _cmake_args(profile),
            cwd=_LLAMA_SRC, timeout=180,
        )
        if rc != 0:
            return ProvisionResult(
                tool=tool, found=False,
                error=f"cmake configure falhou (rc={rc}):\n{tail[-500:]}",
                elapsed_s=round(time.monotonic() - t0, 2),
            )
    else:
        print("  [1/2] CMakeCache.txt já existe, pulando configure.", flush=True)

    # 2. build
    print(f"  [2/2] compilando {tool} (pode levar 2-4 min)...", flush=True)
    rc, tail = _run_live(
        ["cmake", "--build", str(_BUILD_DIR),
         "--config", "Release", "--target", tool],
        cwd=_LLAMA_SRC, timeout=600,
    )
    if rc != 0:
        return ProvisionResult(
            tool=tool, found=False,
            error=f"build falhou (rc={rc}):\n{tail[-500:]}",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    found = find_tool(tool)
    if found is None:
        return ProvisionResult(
            tool=tool, found=False,
            error=f"build rc=0 mas {tool} não encontrado em bin/ nem native/",
            elapsed_s=round(time.monotonic() - t0, 2),
        )

    return ProvisionResult(
        tool=tool, found=True, path=found, built=True,
        elapsed_s=round(time.monotonic() - t0, 2),
    )


def provision(
    tools: list[str] | None = None,
    *,
    profile: str = "auto",
    check_only: bool = False,
) -> list[ProvisionResult]:
    names = tools or ["llama-quantize"]
    results: list[ProvisionResult] = []
    for name in names:
        if name not in _TARGETS:
            results.append(ProvisionResult(
                tool=name, found=False,
                error=f"target desconhecido: {name} (válidos: {list(_TARGETS)})",
            ))
            continue
        if check_only:
            p = find_tool(name)
            results.append(ProvisionResult(tool=name, found=p is not None, path=p))
        else:
            results.append(build_tool(name, profile=profile))
    return results
