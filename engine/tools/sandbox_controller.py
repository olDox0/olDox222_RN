# -*- coding: utf-8 -*-
"""
SandboxController — API central de controle do sandbox ORN.

Responsabilidades:
- Gerenciar o ciclo de vida do QEMU.
- Inicializar o Alpine sob demanda.
- Provisionar ferramentas.
- Executar comandos e código.
"""

from __future__ import annotations

from typing import Sequence

from engine.tools.qemu_daemon import QemuDaemon, DaemonStatus
from engine.tools.qemu_sandbox import SandboxResult


class SandboxControllerError(RuntimeError):
    """Erro operacional do Sandbox Controller."""


class SandboxController:

    def __init__(
        self,
        boot_timeout: int = 180,
        boot_mode: str = "disk",
    ) -> None:
        self.boot_timeout = max(1, int(boot_timeout))
        self.daemon = QemuDaemon()
        self.daemon.boot_mode = boot_mode

    # --------------------------------------------------
    # Estado e ciclo de vida
    # --------------------------------------------------

    def status(self) -> DaemonStatus:
        """Consulta o estado sem iniciar a VM."""
        return self.daemon.status()

    def ensure_online(self) -> DaemonStatus:
        """Garante que o QEMU esteja operacional."""
        status = self.daemon.status()

        if status.online:
            return status

        if not self.daemon.start(timeout=self.boot_timeout):
            raise SandboxControllerError(
                "Falha ao iniciar QEMU. "
                "Consulte: orn sandbox probe -w serial"
            )

        status = self.daemon.status()

        if not status.online:
            raise SandboxControllerError(
                "QEMU iniciou, mas não confirmou estado operacional."
            )

        return status

    def start(self) -> DaemonStatus:
        """Inicia o ambiente se necessário."""
        return self.ensure_online()

    def stop(self) -> None:
        """Encerra o QEMU."""
        self.daemon.stop()

    # --------------------------------------------------
    # Provisionamento
    # --------------------------------------------------

    def bootstrap(self) -> bool:
        """Garante a inicialização e executa o provisionamento."""
        self.ensure_online()

        if not self.daemon.bootstrap():
            raise SandboxControllerError(
                "Falha no provisionamento do Alpine."
            )

        return True

    # --------------------------------------------------
    # Comunicação
    # --------------------------------------------------

    def shell(
        self,
        command: str,
        timeout: float = 30.0,
    ) -> str:
        """Executa comando administrativo no Alpine."""
        self.ensure_online()
        return self.daemon.shell(command, timeout=timeout)

    # --------------------------------------------------
    # Execução de código
    # --------------------------------------------------

    def run(
        self,
        code: str,
        args: Sequence[str] | None = None,
        timeout: int = 120,
        lang: str = "c",
    ) -> SandboxResult:
        """Executa C ou Python como usuário sem privilégios no Alpine."""
        import base64
        import re
        import shlex
        import uuid

        if lang not in ("c", "python"):
            raise ValueError(f"Linguagem não suportada: {lang}")

        if not isinstance(code, str):
            raise TypeError("code deve ser uma string")

        timeout = int(timeout)
        if not 1 <= timeout <= 300:
            raise ValueError("timeout deve estar entre 1 e 300 segundos")

        code_bytes = code.encode("utf-8")
        if len(code_bytes) > 256 * 1024:
            raise ValueError("Código excede o limite de 256 KiB")

        self.ensure_online()

        job_id = uuid.uuid4().hex
        job_dir = f"/workspace/.orn_runs/{job_id}"

        source_name = "main.c" if lang == "c" else "main.py"
        encoded_code = base64.b64encode(code_bytes).decode("ascii")

        out_tag = f"__ORN_{job_id}_OUT__"
        err_tag = f"__ORN_{job_id}_ERR__"
        rc_tag = f"__ORN_{job_id}_RC__="

        args_text = " ".join(
            shlex.quote(str(arg)) for arg in (args or [])
        )

        if lang == "c":
            execution = (
                f"timeout {timeout} ./program {args_text}"
            ).rstrip()
            compile_step = f"""
timeout {timeout} gcc main.c -o program > .compile.stdout 2> .compile.stderr
rc=$?
if [ "$rc" -ne 0 ]; then
    cat .compile.stdout > .stdout
    cat .compile.stderr > .stderr
else
    {execution} > .stdout 2> .stderr
    rc=$?
fi
"""
        else:
            execution = (
                f"timeout {timeout} python3 main.py {args_text}"
            ).rstrip()
            compile_step = f"""
{execution} > .stdout 2> .stderr
rc=$?
"""

        runner = f"""#!/bin/ash
cd {shlex.quote(job_dir)} || exit 125
: > .stdout
: > .stderr

# Limites por execução
limit_failed=0

ulimit -t 60 || limit_failed=1
ulimit -f 32768 || limit_failed=1
ulimit -n 64 || limit_failed=1
ulimit -u 32 || limit_failed=1
ulimit -v 262144 || limit_failed=1

# Não executar se algum limite falhar
if [ "$limit_failed" -ne 0 ]; then
    printf '%s\\n' 'Falha ao aplicar limites de execução' > .stderr
    rc=125
else
{compile_step}
fi

printf '\\n%s\\n' '{out_tag}'
head -c 65536 .stdout | base64

printf '\\n%s\\n' '{err_tag}'
head -c 65536 .stderr | base64

printf '\\n%s%d\\n' '{rc_tag}' "$rc"
"""

        encoded_runner = base64.b64encode(
            runner.encode("utf-8")
        ).decode("ascii")

        qdir = shlex.quote(job_dir)
        qsource = shlex.quote(f"{job_dir}/{source_name}")
        qrunner = shlex.quote(f"{job_dir}/run.sh")

        setup = (
            "mkdir -p /workspace/.orn_runs && "
            "chown root:root /workspace/.orn_runs && "
            "chmod 755 /workspace/.orn_runs && "
            f"mkdir {qdir} && "
            f"printf '%s' '{encoded_code}' | base64 -d > {qsource} && "
            f"printf '%s' '{encoded_runner}' | base64 -d > {qrunner} && "
            f"chown -R orn:orn {qdir} && "
            f"chmod 700 {qrunner} && "
            f"su -s /bin/ash -c "
            f"{shlex.quote(f'cd {job_dir} && ./run.sh')} orn"
        )

        try:
            response = self.daemon.shell(
                setup,
                timeout=(timeout * 2) + 30,
            )

            if out_tag not in response or err_tag not in response:
                return SandboxResult(
                    False, "", 
                    f"Resposta incompleta do sandbox: {response[-2000:]}",
                    -1,
                )

            out_segment = response.split(out_tag, 1)[1].split(
                err_tag, 1
            )[0]

            err_segment = response.split(err_tag, 1)[1].split(
                rc_tag, 1
            )[0]

            rc_match = re.search(
                re.escape(rc_tag) + r"(-?\d+)",
                response,
            )

            if not rc_match:
                return SandboxResult(
                    False, "", "Código de retorno ausente.", -1
                )

            def decode_output(segment: str) -> str:
                raw = "".join(segment.split())
                if not raw:
                    return ""
                return base64.b64decode(raw).decode(
                    "utf-8", errors="replace"
                )

            stdout = decode_output(out_segment)
            stderr = decode_output(err_segment)
            exit_code = int(rc_match.group(1))

            return SandboxResult(
                success=(exit_code == 0),
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )

        finally:
            try:
                self.daemon.shell(
                    f"rm -rf {qdir}",
                    timeout=10,
                )
            except Exception:
                pass

