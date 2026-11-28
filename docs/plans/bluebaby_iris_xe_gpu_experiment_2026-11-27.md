# Experimento futuro — Intel Iris Xe Graphics no Bluebaby

**Data do planejamento:** 2026-11-27  
**Status:** planejado; iniciar somente após concluir a etapa CPU/ORN no Alpine  
**Máquina-alvo:** Bluebaby — inventário associado ao Intel Core i5-1235U  
**Experimento CPU relacionado:** [EXP-010 — CPU/SIMD no Alpine/QEMU](../research/alpine_qwen_cpu_simd_benchmark_2026-11-27.md)

## 1. Objetivo

Investigar se a GPU integrada Intel Iris Xe Graphics do Bluebaby pode acelerar inferência do ORN/llama.cpp, comparando execução CPU-only e GPU offload com o mesmo GGUF e parâmetros equivalentes.

O primeiro teste deve ocorrer **diretamente no Windows hospedeiro**, sem QEMU. A VM Alpine atual não foi configurada com passthrough de GPU nem com dispositivo de computação virtual utilizável. Tentar usar SYCL dentro do guest antes de resolver esse caminho misturaria duas pesquisas diferentes: suporte do backend e virtualização da GPU.

## 2. Hardware e correção da identificação

Dados informados pelo operador:
- Adaptador exibido pelo Windows: `Intel(R) Iris(R) Xe Graphics`.
- Versão de driver informada: `32.0.101.7088`.
- Host associado ao Bluebaby: Intel Core i5-1235U, 10 núcleos / 12 threads lógicos.

A ficha oficial Intel do i5-1235U lista:
- GPU: **Intel Iris Xe Graphics eligible**;
- frequência dinâmica máxima: 1,20 GHz;
- **80 Execution Units (EUs)**;
- OpenCL 3.0;
- 2 mecanismos de codec multiformato;
- suporte a até 4 monitores;
- device ID informado na ficha: `0x46A8`.

**Correção importante sobre “4 sistemas de processamento”:** a ficha técnica não descreve quatro unidades de processamento da GPU. O número 4 corresponde ao máximo de monitores suportados. A GPU é especificada com 80 EUs; há ainda 2 mecanismos de codec multiformato. A versão `32.0.101.7088` identifica o driver, não a quantidade de motores de computação.

A arquitetura Iris Xe LP descreve cada EU como um bloco de execução multithreaded. Portanto, a unidade relevante para a avaliação de compute é o total de EUs, não a quantidade de saídas de vídeo.

**Condição importante de elegibilidade:** a Intel informa que a marca Iris Xe exige memória de 128 bits (dois canais); em configuração de canal único, a marca indicada é Intel UHD. Portanto, é necessário confirmar a configuração de memória real do Bluebaby, apesar de o Windows já reportar “Intel(R) Iris(R) Xe Graphics”. **Ainda precisa ser confirmado no equipamento:** ID PCI/Device Manager real, nome apresentado pelo driver, quantidade de EUs reconhecida pelo runtime, velocidade/configuração dos canais da RAM e memória compartilhada disponível.

## 3. Viabilidade preliminar

O backend SYCL do llama.cpp declara suporte a GPUs integradas Intel em CPUs Core de 11ª geração ou mais novas. A tabela de dispositivos verificados inclui iGPUs Intel de gerações próximas, mas não lista especificamente o i5-1235U. Portanto, a família é candidata compatível; a confirmação do SKU dependerá de descoberta e execução real no Bluebaby.

A documentação do llama.cpp recomenda pelo menos 80 EUs para que o desempenho de inferência em iGPU tenha perspectiva de uso prático. O i5-1235U aparece com exatamente 80 EUs na ficha oficial — atinge o limiar citado, mas isso não garante velocidade competitiva.

A iGPU usa memória compartilhada do sistema. O limite prático depende da RAM disponível, largura de banda e configuração de canais, além de buffers do modelo. A Intel usa como exemplo que um modelo 7B Q4 exige vários GB de memória compartilhada; por isso, começar com o Qwen2.5-Coder-0.5B Q2_K já utilizado no EXP-010 reduz o risco e permite manter o mesmo checksum para a comparação.

## 4. Backend prioritário

**Primeira opção: llama.cpp com backend SYCL para Intel GPU.**

Componentes a investigar:
- driver gráfico Intel compatível com o runtime oneAPI escolhido;
- Intel oneAPI Toolkit (DPC++/C++, runtime SYCL/Level Zero e dependências oneMKL);
- backend SYCL de llama.cpp;
- ferramenta `sycl-ls` para enumerar dispositivos;
- opcionalmente `clinfo` para inspecionar a plataforma OpenCL.

Gate de descoberta: `sycl-ls` deve listar a Iris Xe como um dispositivo GPU Level Zero. A simples presença do driver de vídeo no Gerenciador de Dispositivos não prova que o runtime de computação esteja funcional.

A versão de driver informada (`32.0.101.7088`) será registrada como estado inicial, não como requisito fixo. As notas do Intel oneAPI 2026.2, atualizadas em 2026-10-22, listam uma versão mais recente de driver cliente para Iris Xe/Arc (`101.8826`). Antes da instalação do toolkit, verificar a matriz de compatibilidade atual e decidir se a atualização é necessária; não atualizar no escuro nem misturar versões durante o benchmark.

## 5. Fases propostas

### G0 — Inventário real do dispositivo

- [ ] Capturar `dxdiag` e propriedades do adaptador via PowerShell/CIM.
- [ ] Registrar PNP Device ID, versão/data do driver, nome do adaptador e estado do dispositivo.
- [ ] Confirmar o iGPU/ID `0x46A8` ou registrar divergência.
- [ ] Registrar RAM instalada, velocidade e configuração single/dual-channel quando disponível.
- [ ] Registrar memória compartilhada/dedicada reportada pelo Windows.
- [ ] Registrar temperatura, clocks e consumo em idle e sob carga, se as ferramentas disponíveis permitirem.

**Gate G0:** hardware e driver identificados sem depender somente de nome comercial.

### G1 — Runtime de computação

- [ ] Selecionar versão de Intel oneAPI e validar matriz de suporte do driver.
- [ ] Instalar apenas componentes necessários ao SYCL.
- [ ] Executar `sycl-ls` e confirmar dispositivo `level_zero:gpu`.
- [ ] Confirmar que a GPU encontrada é a Iris Xe do Bluebaby.
- [ ] Executar uma amostra de backend/compute antes de carregar um modelo.

**Gate G1:** runtime enumera a GPU e conclui uma operação de teste sem fallback silencioso para CPU.

### G2 — llama.cpp SYCL no Windows hospedeiro

- [ ] Fixar um commit de llama.cpp que contenha o backend SYCL compatível.
- [ ] Construir o backend SYCL separadamente do wheel CPU experimental do Alpine.
- [ ] Confirmar no log o backend/dispositivo selecionado e as camadas efetivamente offloaded.
- [ ] Executar o Qwen2.5-Coder-0.5B Q2_K identificado no EXP-010.
- [ ] Testar offload desativado, parcial e máximo; registrar o número de camadas transferidas.

**Gate G2:** inferência concluída com evidência explícita de execução na GPU, não apenas enumeração do dispositivo.

### G3 — Benchmark CPU vs. GPU no mesmo host

- [ ] Construir/usar uma referência CPU Windows a partir do mesmo commit do llama.cpp.
- [ ] Usar o mesmo GGUF e SHA256.
- [ ] Fixar contexto, batch, ubatch, threads, seed, prompt e tokens de saída.
- [ ] Separar cold start, warm-up e pelo menos cinco amostras medidas.
- [ ] Registrar tokens/s de prefill/decode, latência, RSS, memória compartilhada, uso da GPU e CPU.
- [ ] Repetir com diferentes níveis de offload e, depois, outro modelo se houver memória suficiente.

**Gate G3:** comparação reproduzível entre CPU e SYCL no Windows, sem misturar com resultados da VM QEMU.

### G4 — Integração ORN

- [ ] Avaliar como o ORN escolhe CPU ou SYCL sem alterar o fallback CPU funcional.
- [ ] Preservar configuração explícita de backend e número de camadas offloaded.
- [ ] Testar a inicialização e encerramento do backend no fluxo real do ORN.
- [ ] Medir estabilidade, memória compartilhada e concorrência com a interface do host.

**Gate G4:** ORN pode usar GPU de forma explícita, diagnosticável e reversível.

## 6. Matriz mínima de benchmark

| Execução | Backend | Dispositivo | GPU layers | Objetivo |
|---|---|---|---:|---|
| A | llama.cpp CPU | i5-1235U CPU | 0 | Baseline host |
| B | llama.cpp SYCL | Iris Xe | parcial | Custo/benefício do offload |
| C | llama.cpp SYCL | Iris Xe | máximo suportado | Limite de aceleração |
| D | llama.cpp CPU | Alpine/QEMU | 0 | Referência separada do EXP-010, não comparação direta |

O relatório deve separar tempo de inicialização e transferência de pesos do tempo de geração com o modelo residente.

## 7. Restrições e riscos

- Não presumir que o driver de vídeo, sozinho, forneça Level Zero/SYCL.
- Não assumir que o backend SYCL está validado especificamente no i5-1235U antes de `sycl-ls` e inferência real.
- Não tentar usar a GPU no Alpine/QEMU atual sem desenvolver e validar um caminho específico de compartilhamento/passthrough.
- Não comprometer a estabilidade do driver Windows usado para vídeo.
- Não comparar o benchmark GPU host com os tokens/s do Alpine/QEMU como se a única variável fosse GPU vs. CPU.
- Não instalar o toolkit completo nem modificar o ambiente ORN de produção antes do inventário e da prova de runtime.

## 8. Referências técnicas

- [Intel — especificações do Core i5-1235U](https://www.intel.com.br/content/www/br/pt/products/sku/226261/intel-core-i51235u-processor-12m-cache-up-to-4-40-ghz/specifications.html)
- [Intel — notas de versão do oneAPI Toolkit 2026.2 (drivers recomendados)](https://www.intel.com/content/www/us/en/developer/articles/release-notes/oneapi-toolkit/2026.html)
- [Microsoft Update Catalog — driver 32.0.101.7088](https://www.catalog.update.microsoft.com/Search.aspx?q=Intel%20Corporation%20-%20Display%2032.0.101.7088)
- [Intel — arquitetura Iris Xe / Execution Units](https://www.intel.com/content/www/us/en/docs/oneapi/optimization-guide-gpu/2023-0/intel-iris-xe-gpu-architecture.html)
- [llama.cpp — backend SYCL](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/SYCL.md)
- [Intel — executar LLMs em GPUs Intel com llama.cpp](https://www.intel.com/content/www/us/en/developer/articles/technical/run-llms-on-gpus-using-llama-cpp.html)
- [Intel — notas do oneAPI Toolkit 2026](https://www.intel.com/content/www/us/en/developer/articles/release-notes/oneapi-toolkit/2026.html)
- [Microsoft Update Catalog — busca do driver Iris Xe](https://www.catalog.update.microsoft.com/Search.aspx?q=Windows%2011%20Intel%20Iris%20Xe%20Graphics%20drivers)

---

**Decisão:** manter o experimento GPU registrado como próxima fase. A prioridade operacional continua sendo concluir a validação do ORN/SiCDoxBridge no Alpine e fechar o benchmark CPU antes de iniciar a instalação de toolchain GPU no Bluebaby.
