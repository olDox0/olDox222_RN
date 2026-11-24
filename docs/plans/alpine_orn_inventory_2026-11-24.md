# ORN Alpine Runtime — Inventário inicial do hospedeiro

**Coletado em:** 2026-11-24 01:21 (-03:00)  
**Origem:** saída de `scripts/alpine_orn_host_inventory.ps1` colada na conversa  
**Checkout:** `C:\Users\Victor Alexandre\Documents\ORN_proj`

## Hospedeiro

| Campo | Valor coletado |
|---|---|
| Equipamento | Dell Inspiron 15 3520 |
| CPU | Intel Core i5-1235U, 12ª geração |
| Núcleos / threads lógicos | 10 / 12 |
| Clock máximo reportado pelo CIM | 1.300 MHz |
| Sistema | Windows 11 Pro |
| Versão / build | 10.0.26300 / 26300 |
| RAM visível | 15,69 GiB |
| RAM livre na coleta | 7,92 GiB |
| Hipervisor detectado pelo Windows | True |
| QEMU | 11.1.0 (v11.0? no; output reports v11.1.0-12130-ge470268ff4) |
| Executável QEMU | `C:\Program Files\qemu\qemu-system-x86_64.exe` |
| Unidade C: livre na coleta | 15,69 GiB |
| Checkout HEAD | `b6b8746e8faa41e8c73b50013a93a9dea9139d65` |

**Atenção:** os 15,69 GiB livres são do volume C: que contém o checkout, não uma medição do espaço livre em todos os discos físicos. A capacidade física informada anteriormente como 125 GB deve ser reconciliada separadamente. O campo `HypervisorPresent=True` indica presença de hipervisor no host, mas não comprova isoladamente que esta execução QEMU usou WHPX.

## QCOW2 existente

| Campo | Valor |
|---|---:|
| Caminho | `data/sandbox/alpine.img.qcow2` |
| Formato | QCOW2 |
| Tamanho virtual | 2 GiB |
| Ocupação física | ~353 MiB |
| Cluster size | 65.536 bytes |
| Corrupt | false |

O tamanho virtual da imagem existente é 2 GiB. O valor de 512 MiB encontrado em `DISK_SIZE_MB` e em `DiskForge` é um default de criação e não descreve o tamanho atual deste arquivo.

## Estado do QEMU na coleta

O inventário inicial registrou logs históricos com invocações em 512 MiB. A primeira consulta ao guest terminou antes da inicialização e informou:

```text
QEMU status: offline (PID 11136 morto)
Guest inventory skipped: start the sandbox first.
```

Depois, o comando `orn sandbox daemon start` iniciou o convidado com sucesso. O log da inicialização registrou:

```text
guest RAM=512 MiB
QEMU ... -accel whpx -accel tcg -m 512M -smp 2 ...
Boot completo detectado.
Socket logado.
online (PID 10232, porta 8373)
```

Portanto, a implementação configurável de RAM ainda não foi aplicada ao processo QEMU desta coleta. A próxima validação deve executar o inventário do guest enquanto o daemon está online, antes de parar a VM.

## Testes já executados

```text
python -m pytest tests/test_qemu_memory_config.py -q
12 passed in 0.20s
```

Isso comprova os testes unitários de parsing/validação da configuração de memória, não a RAM efetiva vista pelo Alpine.

## Pendências

- [ ] Reexecutar `python scripts/alpine_orn_guest_inventory.py` com QEMU online.
- [ ] Confirmar disco/partição/filesystem, `mount`, `df -h` e `/etc/fstab`.
- [ ] Criar e validar sentinela de persistência após identificar o caminho persistente.
- [ ] Aplicar `ORN_QEMU_RAM_MB=1280`, reiniciar e conferir `free -h`.
- [ ] Confirmar aceleração WHPX ou TCG efetivamente utilizada.
- [ ] Medir as flags de CPU expostas pelo host e pelo guest.
- [ ] Fazer backup verificável do QCOW2 antes de qualquer expansão.
