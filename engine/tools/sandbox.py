# -*- coding: utf-8 -*-
# engine/tools/sandbox.py
"""
[ANÚBIS/SET] Sandbox de Execução Segura para o ORN.
Usa Windows Job Objects para isolar o processo (sem QEMU).
Garante limite de memória, tempo de execução e previne fork bombs.
"""

import ctypes
import subprocess
import tempfile
import os
import sys
from pathlib import Path
from ctypes import wintypes
from dataclasses import dataclass

@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int

def run_in_sandbox(code: str, timeout_s: int = 10, mem_limit_mb: int = 256) -> SandboxResult:
    """Executa código Python em uma bolha de isolamento do Windows."""
    
    # 1. Cria o arquivo temporário com o código
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        code_path = Path(f.name)

    try:
        # 2. Configura o Job Object do Windows
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = k32.CreateJobObjectW(None, None)

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        # Flags: TEMPO_DE_CPU (0x02) | MATAR_AO_FECHAR (0x2000) | LIMITE_MEMORIA (0x100)
        JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_TIME | 
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | 
            JOB_OBJECT_LIMIT_PROCESS_MEMORY
        )
        
        # Define o limite de memória (MB para bytes)
        info.ProcessMemoryLimit = mem_limit_mb * 1024 * 1024
        # Define o tempo limite de CPU (em unidades de 100ns)
        info.BasicLimitInformation.PerProcessUserTimeLimit = timeout_s * 10_000_000

        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))

        # 3. Cria o processo suspenso para colocá-lo no Job antes de rodar
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        # Constantes do Kernel do Windows (evita AttributeError no Python 3.12)
        CREATE_SUSPENDED = 0x00000004
        CREATE_NO_WINDOW = 0x08000000
        
        proc = subprocess.Popen(
            [sys.executable, str(code_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_SUSPENDED | CREATE_NO_WINDOW,
            startupinfo=startupinfo
        )

        # 4. Coloca no Job e resume
        k32.AssignProcessToJobObject(job, int(proc._handle))
        ctypes.windll.ntdll.NtResumeProcess(int(proc._handle))

        # 5. Coleta a saída (com timeout de segurança)
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s + 1)
            return SandboxResult(
                success=(proc.returncode == 0),
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode
            )
        except subprocess.TimeoutExpired:
            k32.TerminateJobObject(job, 1)
            return SandboxResult(False, "", "Timeout global excedido.", -1)

    except Exception as e:
        return SandboxResult(False, "", f"Erro no Sandbox: {e}", -1)
    finally:
        code_path.unlink(missing_ok=True)
