# ORN Telemetry API (v1)

Este documento define a API inicial de telemetria para o ORN, com foco em baixo overhead e falha silenciosa.

## Objetivo

A API permite instrumentar funções críticas via `@orn_probe`, agregar métricas em memória e persistir snapshots locais em JSON.

## API

### Decorator: `orn_probe`

```python
from engine.telemetry import orn_probe

@orn_probe(category="exec", critical=True)
def dispatch_node(node):
    ...
```

Parâmetros:

- `category`: classe lógica da sonda (`exec`, `import`, `stability`, etc.).
- `critical`: sinaliza função de alto impacto sistêmico.
- `probe_name`: nome customizado da métrica (opcional).
- `aggregator`: agregador customizado (opcional; padrão: `GLOBAL_TELEMETRY`).

### Agregador: `TelemetryAggregator`

Métodos principais:

- `snapshot() -> dict`: retorna métricas agregadas por probe.
- `flush_json(path) -> Path`: persiste snapshot em JSON compacto.

Formato de saída por probe:

```json
{
  "category": "exec",
  "critical": true,
  "calls": 12031,
  "avg_ms": 0.08,
  "p95_ms": 0.22,
  "max_ms": 1.93,
  "cold_calls": 1,
  "warm_calls": 12030,
  "failures": 0
}
```

## Garantias

1. Telemetria nunca altera resultado funcional.
2. Falhas internas de telemetria são suprimidas.
3. Coleta local-first (sem rede).
4. Overhead reduzido (medição por `time.perf_counter` + contadores numéricos).

## Próximos passos

1. Ligar `@orn_probe` nos hot paths reais do ORN.
2. Definir schema opcional em SQLite para histórico.
3. Alimentar o classificador de performance (OPI) com os snapshots.

## Telemetria no servidor (STATUS)

O endpoint `STATUS` do `orn-server` inclui o campo `telemetry_hotspots`, com os gargalos ordenados por custo total (`calls * avg_ms`).

Exemplo:

```json
{
  "status": "online",
  "system_perf": {
    "pid": 8124,
    "threads": 7,
    "cpu_count": 8,
    "rss_mb": 512.3,
    "load_1m": 0.82
  },
  "ai_perf": {
    "infer_calls": 124,
    "last_infer_s": 1.42,
    "last_tokens_per_s": 90.1,
    "total_tokens_per_s": 72.4,
    "avg_prompt_chars": 312.4,
    "avg_output_chars": 421.8,
    "last_lock_wait_ms": 0.7,
    "last_llm_call_ms": 1410.5,
    "last_non_llm_ms": 9.5,
    "last_llm_share_pct": 99.3
  },
  "telemetry_hotspots": [
    {"name": "server.infer.llm_call", "calls": 124, "avg_ms": 85.2, "p95_ms": 131.4, "total_ms": 10564.8}
  ]
}
```

No shutdown do servidor, um snapshot local também é persistido em `telemetry/server_runtime.json` para análise offline.


## Comandos de acesso rápido

- `orn probe status`: consulta STATUS do servidor e mostra hotspots.
- `orn probe status --json-output`: imprime payload bruto em JSON (inclusive offline).
- `orn probe status --json-output --out .\telemetry\probe_status.json`: salva JSON em arquivo (Windows-friendly).
- `orn probe status --strict`: retorna código 1 quando servidor está offline.
- `orn probe status --limit N`: limita quantidade de hotspots exibidos.
- `orn-probe --json [--limit N] [--out ARQUIVO]`: utilitário dedicado para consumo em scripts.


### Exemplos no Windows (cmd.exe)

No `cmd.exe`, use comandos separados (ou `&&`) em vez de sintaxe Bash com `; rc=$?`.

```bat
python -m engine probe status --json-output --strict --out telemetry\probe_status.json
type telemetry\probe_status.json
echo %ERRORLEVEL%
```


- `ai_perf` resume métricas práticas da IA (throughput, tamanhos médios de prompt/saída e última inferência).


- Quando o servidor retorna schema antigo, `orn probe status` entra em modo `compat` e deriva alguns campos de `ai_perf` a partir de `telemetry_hotspots` (evita zeros enganosos).

- `system_perf` fornece contexto do processo/sistema (threads, CPU, memória RSS, load), útil para correlacionar gargalos de IA com saturação do host.
