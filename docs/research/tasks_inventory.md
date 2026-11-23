# Inventário — Sistema de Tarefas (Cap 0, 2026-11-22)

## Estado real (pré-integração)

### engine/tasks/cli.py — 5 comandos, todos in-process
| Comando | Fluxo | Mutação |
|---|---|---|
| task run <goal> | store.new → runner.run(id) | cria task + executa |
| task list | store.list | read-only |
| task show <id> | store.load | read-only |
| task resume <id> | load → runner.run | reexecuta |
| task abort <id> | can_transition → ABORTED | única mutação de controle |

**Fases:** plan → draft → implement → sandbox → present (série)
**TaskStatus:** PENDING, RUNNING, DONE, BLOCKED, ABORTED (confirmar FAILED)
**Emitter:** _create_event_emitter() → emit(dict) com task_id, phase, attempt,
  code_len, attempts, reason, status
**Kinds emitidos:** task_start, phase_start, phase_done, phase_error, task_done

### engine/tools/server_client.py
- TCP cru JSON \n-delimited, HOST=127.0.0.1, PORT=8371
- _sandbox_call dispatch por {"sandbox": <cmd>, ...} — slot pronto para {"task": ...}
- NÃO existe task_send/task_stream

### engine/web/web_proxy.py (Cap 0.7 — 2026-11-22)
- Framing NDJSON sobre TCP, recv(65536), \n-terminated
- "stream": True hardcoded → não reusa para task
- Timeouts: STREAM_POLL_TIMEOUT_S=1.0, STREAM_READ_TIMEOUT_S=180 (env)
- Retorno: Iterator[dict] (facade._server_stream adapta p/ StreamEvent)

## Gap analysis → Cap 1/2
| Aspecto | Hoje | Alvo §A |
|---|---|---|
| Dono do estado | CLI in-process | Server |
| Runner | CLI | Server handler {"task": "run"} |
| Eventos | dict cru | StreamEvent estendido (§1.1 fix) |
| Streaming | emit sync | NDJSON incremental (_stream_ndjson) |
| Comandos | run/list/show/resume/abort | + start/stop/pause/status |
| TaskStatus | sem PAUSED | + PAUSED (Cap 1.5) |

## Decisões §A (consolidadas 2026-11-22)
1. Task vive/survive exit conforme contexto → modos server/local/ephemeral
2. Server dono, CLI painel de controle
3. Fases em série (paralelismo só Cap 4.6)
4. Web sem auth (read-only) → TASK_W01
5. Estender StreamEvent (aditivo)

## Achados / pendências
- TASK_E06: events.py descarta kinds de task (fix Cap 1)
- TASK_E07: facade._server_stream passa port= (fix Cap 1.8)
- stream_infer_events hardcodes {"stream": True} → refactor Cap 2.0
- server_client.ask() inlina apply_code_hook com stubs falsos (fora de escopo)
