# ORN no Alpine/QEMU — validação do SiCDoxBridge

Data: 25/11/2026  
Branch de trabalho: `linux-alpine-sicdox-bridge`  
Base: `ed731f19089b395643675d800ee48262d455043c`

## Ambiente já validado

- Alpine Linux 3.24.4, x86_64, dentro do QEMU.
- CPU virtual genérica com MMX/SSE/SSE2; sem SSSE3, SSE4.x ou AVX. O binding deve ser compilado para baseline x86-64, sem detecção nativa de instruções do host.
- Python 3.14.10, GCC/G++ 15.2.0, CMake 4.2.3 e Ninja 1.13.2.
- `llama-cpp-python` 0.3.38 compilado localmente com backend CPU, sem OpenMP e sem instruções acima de SSE2.
- O GGUF `SmolLM2-135M-Instruct-Q4_K_M.gguf` foi transferido para `/opt/orn-models/` e o SHA256 conferiu com o arquivo do host: `ed5fa30c487b282ec156c29062f1222e5c20875a944ac98289dbd242e947f747`.

O teste isolado já confirmou carga e geração pelo `llama_cpp.Llama`. Isso comprova o backend de inferência, não a qualidade do modelo: o SmolLM2-135M falhou em seguir instruções simples e deve ser tratado apenas como smoke test. O Qwen2.5-Coder-0.5B disponível no host é o próximo modelo mais representativo para a integração funcional.

## Configuração do bridge

Defina explicitamente o GGUF e desative a biblioteca nativa enquanto o teste usa `llama-cpp-python`:

```sh
export ORN_MODEL_PATH=/opt/orn-models/SmolLM2-135M-Instruct-Q4_K_M.gguf
export ORN_NATIVE_BACKEND=0
export ORN_MEMORY_PROFILE=low
```

O caminho `ORN_MODEL_PATH` agora é aplicado pelo `BridgeConfig` quando nenhum caminho explícito é passado ao construtor. Um caminho passado diretamente em `BridgeConfig(model_path=...)` tem precedência sobre a variável de ambiente. `ORN_NATIVE_BACKEND=0` desativa tanto a inicialização explícita quanto a descoberta automática de biblioteca nativa; sem esse valor, a descoberta procura `orn.dll` no Windows, `liborn.dylib`/ `orn.dylib` no macOS e `liborn.so`/ `orn.so` em Linux.

Configuração recomendada para o primeiro teste no guest de 1,2 GiB:

```python
from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge

cfg = BridgeConfig(
    n_ctx=512,
    active_window=192,
    n_batch=32,
    n_threads=2,
    n_threads_batch=2,
    n_gpu_layers=0,
    max_tokens=24,
    response_hard_limit=128,
    temperature=0.0,
    top_p=1.0,
    repeat_penalty=1.0,
    use_mmap=True,
    use_mlock=False,
    no_alloc=False,
    cont_batching=False,
    flash_attn=False,
    rope_freq_base=None,
)

bridge = SiCDoxBridge(cfg)
try:
    print(bridge.ask("Responda em uma palavra: OK.", max_tokens=24))
    print(bridge.stats())
finally:
    bridge.shutdown()
```

Para facilitar instalações em ambientes com suporte de compilação, o projeto expõe a dependência de inferência como extra opcional:

```sh
python -m pip install -e '.[llm]'
```

No Alpine/QEMU, a compilação do binding continua sendo uma etapa consciente e específica da CPU virtual. Não use `GGML_NATIVE=ON` nesse guest genérico; mantenha desativados AVX/AVX2, SSE4.x, FMA e F16C. O extra Python não substitui a seleção correta das flags CMake.

## Critério para concluir a integração

1. Importar `BridgeConfig` e `SiCDoxBridge` a partir da árvore do ORN no guest.
2. Carregar o modelo por `ORN_MODEL_PATH` sem tentar carregar `orn.dll`.
3. Executar `ask()`, receber texto não vazio, consultar `stats()` e executar `shutdown()` sem traceback.
4. Repetir com o Qwen2.5-Coder-0.5B e fazer pelo menos duas chamadas sequenciais para verificar contexto e liberação.
5. Comparar latência apenas mantendo modelo, quantização, contexto e versão do llama.cpp constantes.

Este documento registra os fatos já observados e o procedimento do próximo marco; os itens 1–4 ainda precisam ser executados usando esta branch atualizada.
