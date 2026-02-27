# ORN — Historia e Atualizacoes v0.2.0
**Volume:** 2 | **Periodo:** 2026.02.21-22 | **Versao:** 0.2.0-server

---

## Contexto

Continuacao direta do Volume 1. A fundacao estava cimentada (27 arquivos,
0 erros de sintaxe, pipeline think validado sem modelo). Esta sessao
resolveu os bloqueios de implantacao real no hardware N2808 e entregou
o servidor de inferencia persistente.

chief_dossier.json (sessao atual):
  Total de arquivos:  72
  engine/ Python:     25 arquivos
  God distribution:   Dionisio 25, Unknown 39, Zeus 5, Atena 1, Hades 1, Poseidon 1

---

## 2026.02.21 — Instalacao Real no N2808

### [INFRA] REP.INFRA.20260209.GOLD arquivado
  Documento: docs/Internals/vol20_infrastructure_report.md
  Protocolo: PASC-8.15 (ArchS) & MPoT-18
  Status: ESTABILIZADO

  Inventario de dependencias confirmado:
    Python          3.12.4
    llama-cpp-python 0.3.16   (compilado via Protocolo Vulcan)
    w64devkit       GCC 15.2  (toolchain de compilacao)
    CMake           4.2.1     (instalacao local no venv)
    Ninja           1.13.0    (backend de build)
    NumPy           2.4.2

  Tres incidentes resolvidos (PASC-1.1):
    3.1 nmake not found -> CMAKE_GENERATOR=MinGW Makefiles
    3.2 GOMP_barrier    -> -DGGML_OPENMP=OFF
    3.3 CMake timeout   -> cmake + ninja instalados no venv

  Flags de compilacao Gold (N2808 SSE4.2):
    CMAKE_ARGS=-DGGML_OPENMP=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF
               -DCMAKE_MAKE_PROGRAM=mingw32-make.exe
               -DCMAKE_C_FLAGS="-msse4.2 -O3"
               -DCMAKE_CXX_FLAGS="-msse4.2 -O3"

  Performance resultante: 0.02 t/s -> 1.40 t/s (ganho 21.5x)

### [FIX] BridgeConfig calibrado para N2808
  n_threads   4 -> 2   (Dual-Core real, OpenMP desativado)
  ttl_seconds 300 -> 3600  (load custa ~80s, manter em RAM)
  max_tokens  512 -> 128   (testes rapidos)
  system_prompt   reformulado: "No introductions. No examples unless asked."

  Bug Python 3.12 prevenido:
    shutdown() agora chama self._llm.close() antes de = None
    Sem isso: TypeError: NoneType no destruidor (REP.INFRA §5.2)

### [FIX] Dois ambientes Python no sistema
  Problema: Python312\ (sistema) vs venv\ — llama_cpp so no venv
  Causa: pip install -e . rodou com o Python errado
  Fix: C:\...\Python312\Scripts\pip uninstall orn -y
       .\venv\Scripts\pip install -e .

### [TOOL] install.py criado
  Verificacao de ambiente em 7 pontos:
    Python >= 3.10, click, numpy, llama-cpp-python,
    llama_cpp.Llama (classe), Modelo GGUF (379MB), orn (pacote)

  Saida VERDE confirmada:
    7/7 verificacoes OK
    Ambiente pronto. Execute: orn config --show

  Extras:
    _check_venv_active(): avisa se rodando fora do venv
    Sem DeprecationWarning do click (usa importlib.metadata)
    Codigo de saida 0 se OK, 1 se criticos (exceto modelo ausente)

### [MVP] Primeira inferencia real — orn think funcionando
  Comando: orn think "explique KV-cache em 3 linhas" --tokens 60
  Resultado: resposta em 166s (60 tokens, ~0.36 t/s)
  Observacao: modelo 0.5B confundiu KV-cache com sistema de storage —
    limitacao real do modelo pequeno para conceitos abstratos.
    Para codigo (bubble sort C): correto e completo.

---

## 2026.02.22 — SiCDox Server

### [SERVER] sicdox_server.py -> engine/server/ pacote
  Problema identificado: modelo recarregando a cada orn think
    Causa: shutdown() no finally do think — 80s de load + inferencia = inutil
    Solucao: servidor persistente que mantem modelo em RAM

  Arquitetura do servidor:
    engine/server/__init__.py    pacote
    engine/server/__main__.py    entry point (orn-server)
    engine/server/server.py      ServerCLI + loop TCP

  Protocolo TCP local porta 8371:
    Request:  JSON linha  {"prompt": "...", "max_tokens": 128}
    Response: JSON linha  {"output": "...", "elapsed_s": 1.23, "error": null}
    Status:   b"STATUS\n" -> JSON com uptime, requests, errors, tokens

  Entry points instalados globalmente:
    orn        = engine.__main__:main   (CLI original)
    orn-server = engine.server.__main__:main

  pyproject.toml atualizado com dois entry points.

### [FIX] Bug de disconnect no server_client.py
  Causa: is_server_online() + ask() = duas conexoes TCP separadas
    Race condition: servidor aceitava a primeira, ficava em estado
    intermediario, segunda conexao falhava
  Fix: ask() vai direto para _raw_query() sem verificacao previa
    Uma unica conexao por requisicao — sem race condition

### [FIX] engine/__main__.py sobrescrito
  Causa: copia dos arquivos do servidor sobrescreveu o __main__.py original
  Fix: restaurado com from engine.cli import cli + def main(): cli()
  Verificacao: orn --help exibe think/audit/brain/config/fix/gen/graph

### [SERVER] engine/tools/server_client.py (Hermes)
  Modulo cliente para uso interno pelo CLI/Executive
  is_server_online(): timeout 1s, retorna bool
  ask(prompt, max_tokens): retorna dict ou None se offline
  status(): retorna dict com metricas ou None
  _raw_query(payload): unica conexao, sem race condition

### [CLI] think command atualizado
  Deteccao automatica do servidor:
    Servidor online  -> "Modo servidor ativo" (sem load)
    Servidor offline -> "Modo direto" (~80s N2808)
    --direct         -> forca modo direto sempre

  Nova opcao: --tokens / -t (limite de tokens por chamada)
  Contexto de arquivo: --file injeta ate 3000 chars no prompt

---

## Resultados de Performance Confirmados

  Primeira carga (cache frio): ~80s
  Carga subsequente (cache quente do SO): 2.8-4.7s
  Inferencia pura (servidor ativo): ~1.4 t/s
  60 tokens via servidor:   ~43s esperado, 135s real (inclui overhead TCP)
  200 tokens via servidor: ~143s esperado, 127s real (bubble sort C correto)

  Nota: overhead de 90s na primeira query via servidor — investigar.
  Hipotese: modelo ainda aquecendo KV-cache na primeira inferencia pos-load.

---

## Incidentes e Resolucoes desta Sessao

  I-001  llama_cpp nao encontrado no venv correto
         Causa: dois Pythons no sistema (venv vs sistema)
         Fix: uninstall do sistema + install no venv

  I-002  UnboundLocalError no install.py (check_click)
         Causa: import importlib.metadata dentro da funcao shadow o global
         Fix: alias local _imeta = importlib.metadata

  I-003  orn think "disconnect" do servidor
         Causa: race condition entre is_server_online() e ask()
         Fix: ask() conecta direto sem verificacao previa

  I-004  engine/__main__.py sobrescrito pelo servidor
         Causa: copy dos arquivos do servidor copiou o __main__ errado
         Fix: restaurar from engine.cli import cli

  I-005  orn-server nao encontrado no PATH
         Causa: PATH nao persiste entre terminais sem activate.bat fixado
         Fix: echo set PATH=%~dp0;%PATH%>> .\venv\Scripts\activate.bat

  I-006  orn-server ModuleNotFoundError engine.server
         Causa: engine/server/__init__.py nao existia no projeto
         Fix: criar __init__.py + __main__.py + copiar server.py

---

## Estado Atual (v0.2.0)

  FASE 1 -- think:    ATIVO com servidor
  FASE 2 -- audit:    planejado
  FASE 2 -- graph:    planejado
  FASE 3 -- brain:    planejado
  FASE 4 -- fix/gen:  planejado

  Comandos operacionais:
    orn-server start          inicia servidor (foreground)
    orn-server start --bg     inicia em background
    orn-server stop           para servidor com .close()
    orn-server status         uptime, requests, tokens
    orn-server ask "prompt"   consulta direta
    orn think "pergunta"      CLI com deteccao automatica de servidor
    orn think "..." --tokens N  controle de tokens por chamada
    orn config --show         verifica ambiente completo
    python install.py         verificacao de 7 pontos do ambiente

  Pendente:
    [ ] Investigar overhead da primeira query via servidor (~90s extra)
    [ ] PATH permanente no activate.bat (echo fixado)
    [ ] sicdox_server.py na raiz -- remover ou manter como legacy?
    [ ] 39 arquivos Unknown sem deus atribuido -- atribuir na Fase 2
    [ ] doxoade canonize "v0.2.0 servidor operacional"
    [ ] doxoade save "Fase 1 completa com servidor"

---

## Decisao Arquitetural: Modelo como Servico

Confirmada na pratica nesta sessao. O servidor prova o principio:
  - Modelo sobe uma vez, serve indefinidamente
  - Core logico (Executive, Validator, Board) independe do modelo
  - Falha na inferencia nao derruba o servidor (OSL-15)
  - .close() explicito previne TypeError do destruidor (REP.INFRA §5.2)
  - n_threads=2 confirmado como teto real no N2808 sem OpenMP

Referencia: REP.INFRA.20260209.GOLD + relatorio de memoria (KV-cache)
  "Nao tente rodar modelos grandes. Faca modelos grandes se comportarem pequenos."

---

*Proximo volume: vol3_atualizacoes_0300.md (Fase 2: audit + graph)*