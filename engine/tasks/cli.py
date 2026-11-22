# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from pathlib import Path
import click

from engine.ui.display import Display
from engine.tasks.model import (
    TaskSpec,
    TaskStatus,
    can_transition_status,
)
from engine.tasks.store import TaskStore, DEFAULT_ROOT
from engine.tasks.factory import build_default_runner


def _create_event_emitter():
    """Retorna um handler para renderizar eventos de streaming no terminal."""
    def _emit(ev: dict) -> None:
        event = ev.get("event")
        phase = ev.get("phase", "")
        attempt = ev.get("attempt")

        if event == "task_start":
            Display.section("TASK", f"ID: {ev.get('task_id')} | Fase: {phase}")
        elif event == "phase_start":
            att_info = f" (tentativa {attempt + 1})" if attempt is not None else ""
            Display.info(f"▶ Fase [{phase.upper()}]{att_info} iniciada...")
        elif event == "phase_done":
            extra = []
            if "code_len" in ev:
                extra.append(f"{ev['code_len']} chars")
            if "attempts" in ev:
                extra.append(f"{ev['attempts']} tentativa(s)")
            extra_str = f" ({', '.join(extra)})" if extra else ""
            Display.success(f"✔ Fase [{phase.upper()}] concluída{extra_str}")
        elif event == "phase_error":
            reason = ev.get("reason", "erro")
            Display.warn(f"⚠ Falha na fase [{phase.upper()}]: {reason}")
        elif event == "task_done":
            status = ev.get("status", "done")
            Display.info(f"■ Execução finalizada | Status: [{status.upper()}]")

    return _emit


@click.group("task")
def task_group() -> None:
    """ORN — Gerenciamento e execução autônoma de tarefas (PLAN ➔ DRAFT ➔ IMPL ➔ SANDBOX ➔ PRESENT)."""
    pass


@task_group.command("run")
@click.argument("goal", nargs=-1, required=True)
@click.option("--workspace", "-w", type=click.Path(file_okay=False), default=str(DEFAULT_ROOT),
              help="Diretório raiz de persistência das tarefas.")
@click.option("--lang", default="python", help="Linguagem alvo (python, c, cpp, etc.).")
@click.option("--max-retries", type=int, default=2, help="Máximo de retries regenerando draft.")
@click.option("--tokens", "-t", type=int, default=None, help="Limite de tokens por geração.")
@click.option("--timeout", type=int, default=None, help="Timeout em segundos no sandbox.")
@click.option("--stream/--no-stream", default=True, help="Exibe progresso em tempo real.")
def task_run(
    goal: tuple[str, ...],
    workspace: str,
    lang: str,
    max_retries: int,
    tokens: int | None,
    timeout: int | None,
    stream: bool,
) -> None:
    """Cria e executa uma tarefa autônoma até a validação em sandbox."""
    goal_text = " ".join(goal).strip()
    if not goal_text:
        Display.error("Objetivo da tarefa não pode ser vazio.", fatal=True)

    store = TaskStore(root=workspace)
    spec = TaskSpec(
        goal=goal_text,
        language=lang,
        max_retries=max_retries,
        max_tokens=tokens,
        timeout_s=timeout,
    )
    task = store.new(spec)

    emitter = _create_event_emitter() if stream else None
    runner = build_default_runner(store, emit=emitter)

    Display.banner()
    Display.thinking(f"Objetivo: {goal_text}")

    t0 = time.perf_counter()
    result_task = runner.run(task.id)
    elapsed = round(time.perf_counter() - t0, 2)

    Display.separator()
    present_art = result_task.artifact("present")
    if present_art and present_art.content:
        print(present_art.content)
    else:
        impl_art = result_task.artifact("implement")
        if impl_art and impl_art.code:
            Display.code_block(impl_art.code, lang=impl_art.lang)

    Display.separator()
    if result_task.status == TaskStatus.DONE:
        Display.success(f"Tarefa {result_task.id} CONCLUÍDA com sucesso em {elapsed}s.")
    elif result_task.status == TaskStatus.BLOCKED:
        Display.warn(f"Tarefa {result_task.id} BLOQUEADA (limite de retries excedido em {elapsed}s).")
        Display.info(f"Use 'orn task resume {result_task.id}' após ajustar contexto.")
    else:
        Display.error(f"Tarefa {result_task.id} FALHOU ({result_task.status.value}).")
        for err in result_task.errors:
            Display.error(f"  • {err}")


@task_group.command("list")
@click.option("--workspace", "-w", type=click.Path(file_okay=False), default=str(DEFAULT_ROOT))
@click.option("--status", type=click.Choice([s.value for s in TaskStatus]), default=None)
def task_list(workspace: str, status: str | None) -> None:
    """Lista tarefas salvas no repositório local."""
    store = TaskStore(root=workspace)
    filter_status = TaskStatus(status) if status else None
    tasks = store.list(status=filter_status)

    Display.section("TASKS", f"{len(tasks)} encontrada(s)")
    if not tasks:
        Display.info("Nenhuma tarefa encontrada.")
        return

    print(f"  {'ID':<26} {'STATUS':<10} {'FASE':<10} {'TENT':<6} {'OBJETIVO'}")
    print("  " + "─" * 76)
    for t in tasks:
        goal_preview = t.spec.goal[:36] + ("..." if len(t.spec.goal) > 36 else "")
        status_color = t.status.value.upper()
        print(f"  {t.id:<26} {status_color:<10} {t.current_phase:<10} {t.attempts:<6} {goal_preview}")
    print()


@task_group.command("show")
@click.argument("task_id")
@click.option("--workspace", "-w", type=click.Path(file_okay=False), default=str(DEFAULT_ROOT))
@click.option("--code", is_flag=True, default=False, help="Exibe o código final implementado.")
def task_show(task_id: str, workspace: str, code: bool) -> None:
    """Exibe detalhes de uma tarefa específica."""
    store = TaskStore(root=workspace)
    try:
        task = store.load(task_id)
    except FileNotFoundError:
        Display.error(f"Tarefa não encontrada: {task_id}", fatal=True)

    Display.section("TASK SHOW", task.id)
    Display.kv("Status", task.status.value.upper())
    Display.kv("Fase Atual", task.current_phase)
    Display.kv("Linguagem", task.spec.language)
    Display.kv("Tentativas", str(task.attempts))
    Display.kv("Objetivo", task.spec.goal)
    created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at))
    Display.kv("Criado em", created_str)

    if task.errors:
        Display.lista("Erros registrados", task.errors)

    if code:
        impl = task.artifact("implement") or task.artifact("draft")
        if impl and impl.code:
            Display.code_block(impl.code, lang=impl.lang)
        else:
            Display.info("Nenhum código gerado para esta tarefa.")
    else:
        present = task.artifact("present")
        if present and present.content:
            Display.separator()
            print(present.content)
            Display.separator()


@task_group.command("resume")
@click.argument("task_id")
@click.option("--workspace", "-w", type=click.Path(file_okay=False), default=str(DEFAULT_ROOT))
@click.option("--stream/--no-stream", default=True)
def task_resume(task_id: str, workspace: str, stream: bool) -> None:
    """Retoma a execução de uma tarefa bloqueada ou interrompida."""
    store = TaskStore(root=workspace)
    try:
        task = store.load(task_id)
    except FileNotFoundError:
        Display.error(f"Tarefa não encontrada: {task_id}", fatal=True)

    if task.status not in (TaskStatus.BLOCKED, TaskStatus.RUNNING, TaskStatus.PENDING):
        Display.error(f"Não é possível retomar tarefa com status '{task.status.value}'.", fatal=True)

    emitter = _create_event_emitter() if stream else None
    runner = build_default_runner(store, emit=emitter)

    Display.section("TASK RESUME", task.id)
    t0 = time.perf_counter()
    res = runner.run(task.id)
    elapsed = round(time.perf_counter() - t0, 2)

    if res.status == TaskStatus.DONE:
        Display.success(f"Tarefa {res.id} concluída com sucesso em {elapsed}s.")
    else:
        Display.warn(f"Tarefa {res.id} finalizou com status: {res.status.value}.")


@task_group.command("abort")
@click.argument("task_id")
@click.option("--workspace", "-w", type=click.Path(file_okay=False), default=str(DEFAULT_ROOT))
def task_abort(task_id: str, workspace: str) -> None:
    """Aborta manualmente uma tarefa pendente ou bloqueada."""
    store = TaskStore(root=workspace)
    try:
        task = store.load(task_id)
    except FileNotFoundError:
        Display.error(f"Tarefa não encontrada: {task_id}", fatal=True)

    if not can_transition_status(task.status, TaskStatus.ABORTED):
        Display.error(f"Não é possível abortar tarefa com status '{task.status.value}'.", fatal=True)

    task.set_status(TaskStatus.ABORTED)
    store.save(task)
    Display.success(f"Tarefa {task_id} abortada com sucesso.")
