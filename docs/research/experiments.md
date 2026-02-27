# ORN — Experiments Log
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## EXP-001 -- Pipeline Validation sem Modelo (2026.02.19)

Objetivo: Validar que o pipeline MVP funciona sem o modelo carregado,
retornando erros gracionsos em vez de traceback.

Metodo:
  python3 -c "
    from engine.core.executive import SiCDoxExecutive
    ex = SiCDoxExecutive()
    result = ex.process_goal('think', 'teste de integracao')
    print(result.success, result.errors, result.metadata)
    ex.shutdown()
  "

Resultado:
  success=False
  errors=['[ARQUIVO] Modelo nao encontrado: models/sicdox/...']
  metadata={'elapsed_s': 0.001}

Conclusao: Pipeline robusto. FileNotFoundError capturado corretamente.
O bridge foi carregado, tentou _load(), detectou ausencia do .gguf,
retornou GoalResult gracioso. OSL-15 funcionando.

---

## EXP-002 -- ContextWindow Sliding Window (2026.02.19)

Objetivo: Verificar que turns antigos sao descartados corretamente.

Metodo:
  ctx = ContextWindow(max_tokens=10)
  ctx.push("user", "palavra " * 8)    # ~8 tokens estimados
  ctx.push("user", "outro " * 8)      # deve descartar o primeiro
  assert len(ctx.get_turns()) == 1

Resultado: PASSOU. Sliding window funcionando.
Turn antigo descartado quando token_est ultrapassou max_tokens.

Observacao: Estimativa por palavras e grosseira.
Na Fase 2, integrar tokenizer real do llama-cpp-python:
  llm.tokenize(content.encode()) -> len() de tokens reais.

---

## EXP-003 -- Validator Python Syntax (2026.02.19)

Objetivo: Verificar que codigo Python invalido e rejeitado antes
de chegar ao usuario.

Casos testados:
  validar_output("def foo(): pass")    -> (True, "")        PASSOU
  validar_output("")                   -> (False, "vazio")  PASSOU
  validar_output("def (:", lang="python") -> (False, "SyntaxError") PASSOU
  validar_output("x = 1 + 2", lang="python") -> (True, "")  PASSOU
  validar_output(None)                 -> (False, "nao str") PASSOU

Todos os 5 casos passaram. Anubis funcionando.

---

## EXP-004 -- pyproject.toml Fix (2026.02.19)

Problema: pip install -e . falhava com BackendUnavailable:
  Cannot import 'setuptools.backends.legacy'

Causa: Python 3.12 + setuptools moderno nao tem o submodulo
"backends.legacy" como caminho de import valido.

Fix: Trocar build-backend para "setuptools.build_meta".
Resultado: pip install -e . bem sucedido apos fix.

---

## EXP-005 -- llama-cpp-python no Windows sem MSVC (2026.02.19)

Problema: pip install llama-cpp-python falha sem compilador C++.
  CMake Error: CMAKE_C_COMPILER not set (nmake nao encontrado)

Causa: llama-cpp-python requer compilacao de codigo C++ via scikit-build-core.
O Windows sem Visual Studio / Build Tools nao tem nmake/cl.exe.

Solucoes identificadas:
  1. Wheel pre-compilada:
     pip install llama-cpp-python
       --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

  2. doxoade w64toolkit (verificar se ja instalou): (recomendada, já temos experiencia nisto)
     python -c "import llama_cpp; print(llama_cpp.__version__)"

  3. Visual Studio Build Tools (pesado, ~4GB):
     https://visualstudio.microsoft.com/visual-cpp-build-tools/

Status: aguardando confirmacao de qual metodo usar no ambiente do projeto.

---

## Proximos Experimentos Planejados

  EXP-006 -- Primeiro orn think real com modelo carregado
    Objetivo: medir tempo de load, token/s, qualidade da resposta.
    Metricas: elapsed_s, ctx_stats, qualidade subjetiva.

  EXP-007 -- ContextWindow com tokenizer real
    Objetivo: comparar estimativa por palavras vs tokens reais.
    Hipotese: estimativa subestima em ~30% para codigo.

  EXP-008 -- n_gpu_layers > 0 se VRAM disponivel
    Objetivo: medir ganho de performance com camadas na GPU.
    Metrica: tokens/segundo vs n_gpu_layers=0.

  EXP-009 -- ConceptMapper no proprio engine/
    Objetivo: gerar seed_graph.json do engine/ atual.
    Prerequisito: Fase 2 implementada.