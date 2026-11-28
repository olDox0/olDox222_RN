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

---

## EXP-010 -- llama.cpp CPU nativo no Alpine/QEMU (2026.11.27)

Objetivo: comparar o wheel genérico x86-64 com um wheel `llama-cpp-python 0.3.38` compilado para a CPU exposta pelo QEMU (`-cpu host,vmx=off`).

Ambiente: Bluebaby / Intel Core i5-1235U; Alpine 3.24.4; QEMU com 2 vCPUs e 2.048 MiB; GCC 15.2.0; Qwen2.5-Coder-0.5B-Instruct Q2_K (SHA256 registrado no relatório).

Build nativo: `-O3 -march=native -mtune=native`, `GGML_NATIVE=ON`, OpenMP/BLAS/CUDA desligados e compilação serial. AVX2, AVX-VNNI, FMA, F16C e BMI2 foram confirmados no backend; smoke test do modelo passou.

Resultados (média de 3 execuções, 2 threads):
- Genérico: prefill 7,566 tok/s; decode 6,511 tok/s; requisição 3,920 tok/s.
- Nativo: prefill 110,199 tok/s; decode 35,961 tok/s; requisição 28,461 tok/s.
- Pico RSS: 507,5 MiB genérico; 637,0 MiB nativo.
- Nativo em 1 thread: prefill 85,358; decode 25,263; requisição 20,516 tok/s.

Conclusão: o perfil nativo teve ganhos expressivos nesta configuração. O ganho é do perfil completo de compilação e não pode ser atribuído a uma instrução isolada. O ORN/SiCDoxBridge ainda não foi validado por este experimento.

Relatório completo: [alpine_qwen_cpu_simd_benchmark_2026-11-27.md](alpine_qwen_cpu_simd_benchmark_2026-11-27.md).

## EXP-011 -- Intel Iris Xe no Bluebaby (planejado)

Objetivo: avaliar inferência com GPU offload via backend SYCL do llama.cpp no Windows hospedeiro, depois de concluída a etapa CPU/ORN no Alpine.

Dado informado: adaptador `Intel(R) Iris(R) Xe Graphics`, driver `32.0.101.7088`. Para o Core i5-1235U, a ficha Intel informa 80 EUs, OpenCL 3.0, dois mecanismos de codec e suporte a até quatro monitores. Os quatro monitores não são quatro unidades de processamento.

Primeiro gate: inventário real do dispositivo e do driver, depois `sycl-ls` com a GPU enumerada via Level Zero. Só então construir llama.cpp com SYCL, executar o mesmo GGUF e comparar CPU vs. GPU no mesmo host.

Plano: [bluebaby_iris_xe_gpu_experiment_2026-11-27.md](../plans/bluebaby_iris_xe_gpu_experiment_2026-11-27.md).
