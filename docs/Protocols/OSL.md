# OSL — olDox222 Software Law
**CR:** 2025.11.26 | **AT:** 2026.02.06 | **Versao:** Powers Edition

Conjunto de regras de qualidade de software adotadas em todos os projetos
olDox222, incluindo o ORN. Derivado e adaptado do Modern Power of Ten.

---

## Regras

### OSL-1 — Fluxo de Controle Simples e Observavel
Evite goto, setjmp/longjmp e recursao nao controlada. Permita excecoes
estruturadas (try/catch) apenas com politicas de erro bem definidas.
Prefira fluxos controlados por estados / finite-state machines.
Como checar: doxoade check --complexity / doxoade style

### OSL-2 — Loops com Limites Provaveis ou Timeouts Verificaveis
Todos os loops devem ter limite superior comprovavel -- por prova
estatica, anotacao de contrato (loop bound) ou timeout/watchdog.
Em algoritmos com complexidade variavel, documente os casos amortizados.
Como checar: anotacoes de pre-condicao; stress tests com sensores de tempo.

### OSL-3 — Alocacao Controlada e Segura
Proiba alocacao dinamica incontrolada em codigo critico apos inicializacao.
Use memory pools, arenas, alocadores com limites, ou alocacao somente no
startup. Se alocacao dinamica for necessaria, exija limites e fallback
deterministico.
No ORN: _llm = None ate _load(); shutdown() libera deterministicamente.

### OSL-4 — Funcoes Curtas e Coesas
Mantenha funcoes em ~60 linhas ou menos como orientacao.
Se precisar de mais, divida em subfuncoes com nomes descritivos.
Priorize clareza sobre contagem exata de linhas.
Como checar: doxoade check (max_function_lines = 60 em pyproject.toml)

### OSL-5 — Assercoes e Contratos Formais
5.1: Use assercoes ou contratos com invariantes, pre/pos-condicoes e
     checagens de erro sem efeitos colaterais.
5.2: Funcoes que recebem dados de IO ou de outros modulos devem validar
     integridade da entrada (ex: if not path: raise ValueError).
5.3: Assercoes e excepts devem ser informativos. Centralizar utilitario
     em tools/ para padronizar mensagens de erro.

### OSL-6 — Escopo Minimo e Imutabilidade
Declare dados no menor escopo pratico. Prefira imutabilidade.
Quando necessario, exponha mutabilidade explicitamente.
No ORN: get_turns() retorna copia; get_summary() retorna copia.

### OSL-7 — Tratamento de Erros Obrigatorio e Contratos de API
Todo retorno de funcao que possa falhar deve ser verificado pelo chamador.
Funcoes devem validar parametros de entrada e documentar contratos.
No ORN: validar_output() retorna (bool, motivo) -- chamador sempre verifica.

### OSL-8 — Macros e Metaprogramacao Restrita
Limite macros a coisas triviais. Prefira funcoes inline, templates/generics.
Evite concatenacao de tokens, macros recursivas.
Minimize diretivas condicionais; prefira feature flags explicitos.

### OSL-9 — Ponteiros e Referencias Seguros
Restrinja uso de ponteiros brutos. Prefira referencias e smart pointers.
Proiba esconder desreferencia em macros/typedefs.

### OSL-10 — Compilacao Rigorosa, CI e Analise Continua
Desde o primeiro commit: compilacao com warnings maximos; build limpo.
Integre: analisadores estaticos, sanitizers, fuzzers, testes unitarios.
doxoade: doxoade check / doxoade canonize / doxoade regression-test

### OSL-11 — Concorrencia Explicitamente Segura
Declare invariantes de thread-safety para cada modulo.
Use tipos thread-safe, locks com escopo minimo.
Prefira imutabilidade e canais/actor-model.

### OSL-12 — Observabilidade e Telemetria com Custos Controlados
Instrumente codigo critico com logs estruturados e metricas.
A telemetria nao deve alterar comportamento (sem efeitos colaterais).
No ORN: stats(), bridge_stats(), board.get_summary() para orn brain.

### OSL-13 — Seguranca da Cadeia de Fornecimento
Pin de versoes, verificacao de assinaturas, SBOM.
Scanner de vulnerabilidades integrado ao CI.
No ORN: requirements.txt com versoes minimas; llama-cpp-python manual.

### OSL-14 — Testes de Propriedade e Fuzzing Continuo
Alem de testes unitarios, incluir property-based tests e fuzzing
para interfaces externas e parsing.

### OSL-15 — Politica de Tolerancia a Falhas e Modos Degradados
Defina modos degradados seguros: fail-stop mensuravel, retorno a estado
seguro, procedimentos de recuperacao documentados.
No ORN: excecoes internas viram GoalResult(success=False) -- nunca
propagam para a CLI como traceback nao tratado.

### OSL-16 — Politica Anti-Monolito
Nao tolerado: scripts monoliticos com funcoes complexas em arquivo unico.
Nao permitido: mais de 500 linhas em Python.
Excecoes: linguagens muito verbosas (C/C++) tem folga maior.
Como checar: doxoade check (max_file_lines = 500 em pyproject.toml)

### OSL-17 — Principio de Responsabilidade
Um unico arquivo nao pode ter excesso de responsabilidade.
As partes devem ser quase independentes.
Um sistema de diagnostico (Diagnostic/) independente e recomendado.
No ORN: cli.py so roteia; executive.py so orquestra; bridge.py so infere.

### OSL-18 — Bibliotecas Padrao
Priorize stdlib da linguagem.
Use bibliotecas externas somente se stdlib nao cumprir o objetivo.
No ORN: ast, os, sys, json, pathlib, ctypes -- tudo stdlib.

### OSL-19 — Quarentena de Testes (Test-Lock)
19.1 Isolamento: tests/ nao pode ser importado por modulos de producao.
19.2 Bloqueio: doxoade run recusa arquivos em tests/ sem --test-mode.
19.3 Assinatura: scripts sensiveis verificam DOXOADE_AUTHORIZED_RUN.

### OSL-20 — Anti-Apocalypse
20.1 Continuity: SEMPRE salvar apos atualizacoes estaveis.
     (Previne incidentes como o Apocalyptic Incident de 2025-02-14)
20.2 Damage Control: ao perder material, liste afetados, verifique git local.
20.3 Recovery: recuperacao cautelosa, priorizando sistemas centrais.
20.4 Backup: backup continuo, mesmo terceirizado via IDE.

---

## Checklist Rapido para ORN

  [ ] CI com analise de complexidade ciclomatica (doxoade check)
  [ ] Funcoes <= 60 linhas, arquivos <= 500 linhas
  [ ] Todo retorno de funcao verificado pelo chamador
  [ ] tests/ isolado -- nunca importado por engine/
  [ ] doxoade canonize antes de releases
  [ ] doxoade save apos atualizacoes estaveis