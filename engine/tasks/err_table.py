# -*- coding: utf-8 -*-
# doxoade/engine/tasks/err_table.py
"""
Tabela de erros previstos do sistema de tarefas (ProDeNov 5.4 / TYPHON).

Cada entrada responde W5: onde, quando, o quê, quem, por quê, origem, consequência.
Fonte única de verdade para fallbacks e sonda TASK_E06 (round-trip de StreamEvent).
Consumida por diagnostics.py, facade.py e events.py (ORN_DEBUG=1).
"""

from __future__ import annotations
from typing import TypedDict


class ErrEntry(TypedDict):
    onde: str; quando: str; o_que: str; quem: str
    porque: str; origem: str; consequencia: str; fallback: str
    severidade: str  # "error" | "warn"


ERROS: dict[str, ErrEntry] = {
    "TASK_E01": {
        "onde": "engine/tasks/facade.py",
        "quando": "start/resume com server offline e sem --local/--ephemeral",
        "o_que": "conexão recusada em 127.0.0.1:8371",
        "quem": "operador",
        "porque": "servidor não iniciado",
        "origem": "server_client.is_server_online() == False",
        "consequencia": "bloqueia execução server-side",
        "fallback": "exigir --local ou --ephemeral explícito (sem fallback silencioso)",
        "severidade": "error",
    },
    "TASK_E02": {
        "onde": "engine/tasks/events_adapter.py",
        "quando": "recebe dict de evento com kind desconhecido",
        "o_que": "kind fora do EventKind Literal",
        "quem": "server (emissor)",
        "porque": "versão dessincronizada cliente/servidor",
        "origem": "StreamEvent.from_raw retorna None",
        "consequencia": "evento é descartado silenciosamente",
        "fallback": "log + ignorar (não corrompe stream)",
        "severidade": "warn",
    },
    "TASK_E03": {
        "onde": "engine/web/tasks_proxy.py",
        "quando": "stream NDJSON quebra no meio",
        "o_que": "socket fechado prematuramente ou timeout",
        "quem": "servidor / rede",
        "porque": "STREAM_READ_TIMEOUT_S excedido ou server crash",
        "origem": "web_proxy.stream_infer_events (branch de timeout)",
        "consequencia": "web perde progresso em tempo real",
        "fallback": "polling 1s via server_client.task_send",
        "severidade": "warn",
    },
    "TASK_E04": {
        "onde": "engine/tasks/server_store.py",
        "quando": "load de task com JSON inválido",
        "o_que": "json.JSONDecodeError ou schema inválido",
        "quem": "disco / escrita interrompida",
        "porque": "escrita parcial ou corrupção",
        "origem": "~/.orn/tasks/<id>.json",
        "consequencia": "task ilegível",
        "fallback": "restaurar .bak + recriar; emit_forensic_log",
        "severidade": "error",
    },
    "TASK_E05": {
        "onde": "engine/tasks/cli.py",
        "quando": "comando exige transição inválida",
        "o_que": "can_transition_status retorna False",
        "quem": "operador",
        "porque": "estado atual não permite a transição",
        "origem": "TaskStatus enum",
        "consequencia": "comando recusado",
        "fallback": "sugerir 'task reset <id>' (Cap 4)",
        "severidade": "error",
    },
    "TASK_E06": {
        "onde": "engine/api/events.py",
        "quando": "to_ndjson/parse_ndjson_line com kinds de tarefa",
        "o_que": "round-trip falha — kind sem branch",
        "quem": "qualquer consumidor de StreamEvent",
        "porque": "EventKind declara 7 kinds sem branch em to_dict/from_raw",
        "origem": "StreamEvent.to_dict / from_raw",
        "consequencia": "evento de tarefa é descartado silenciosamente",
        "fallback": "erro no boot se ORN_DEBUG=1",
        "severidade": "error",
    },
    "TASK_E07": {
        "onde": "engine/api/facade.py:_server_stream",
        "quando": "facade.ask_stream com prefer=server e server online",
        "o_que": "TypeError: unexpected keyword argument 'port'",
        "quem": "consumidor da InferenceFacade",
        "porque": "assinatura de web_proxy.stream_infer_events usa 'infer_port'",
        "origem": "chamada stream_infer_events(..., port=_P)",
        "consequencia": "stream server-side inoperante (dead code)",
        "fallback": "renomear kwarg para infer_port=_P (Cap 1.8)",
        "severidade": "error",
    },
    "TASK_E08": {
        "onde": "engine/tasks/runner.py",
        "quando": "modelo emite '| stopgen |' no output",
        "o_que": "terminador legítimo mal-classificado como leak de prompt",
        "quem": "modelo (emissor) → runner (receptor)",
        "porque": "_LEAKED_MARKERS listava '| stopgen |' junto com [CRIATORES]",
        "origem": "runner._has_leaked_markers + _phase_plan retry",
        "consequencia": "plano válido é rejeitado 3× → task FAILED",
        "fallback": "_strip_end_markers remove antes de validar; só "
                    "[CRIATORES]/[COMANDA]/[RESULTADO]/[END] são leaks",
        "severidade": "error",
    },
    "TASK_W01": {
        "onde": "engine/web/tasks_proxy.py",
        "quando": "web consome tasks sem auth (decisão §A.4)",
        "o_que": "ausência de autenticação",
        "quem": "usuário da rede local",
        "porque": "v1 aceita read-only sem auth",
        "origem": "decisão §A.4",
        "consequencia": "observação de tasks por qualquer host local",
        "fallback": "read-only; auth em versão futura",
        "severidade": "warn",
    },
}


def get(code: str) -> ErrEntry | None:
    return ERROS.get(code)


def render(code: str) -> str:
    e = ERROS.get(code)
    if not e:
        return f"[{code}] (código desconhecido)"
    lines = [f"[{code}] ({e['severidade'].upper()}) {e['o_que']}"]
    for k in ("onde", "quando", "quem", "porque", "origem",
              "consequencia", "fallback"):
        lines.append(f"  {k:<12} {e[k]}")
    return "\n".join(lines)


def _run_tests() -> int:
    passed = failed = 0
    def _chk(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}"); passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else "")); failed += 1
    _chk("ERROS tem 8 entradas", len(ERROS) == 8)
    _chk("todos prefixo TASK_", all(c.startswith("TASK_") for c in ERROS))
    req = {"onde", "quando", "o_que", "quem", "porque", "origem",
           "consequencia", "fallback", "severidade"}
    for code, e in ERROS.items():
        _chk(f"{code} campos completos", req <= set(e))
    _chk("get(E06) ok", get("TASK_E06") is not None)
    _chk("get(XX) → None", get("TASK_XX") is None)
    _chk("render(E01) tem tag", "[TASK_E01]" in render("TASK_E01"))
    _chk("render(XX)", "desconhecido" in render("TASK_ZZ"))
    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK"); return 0
    print(f"  {passed}/{passed + failed} — {failed} falha(s)"); return 1


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    for code in sorted(ERROS):
        print(render(code)); print()
