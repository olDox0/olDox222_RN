# ORN — História e Atualizações (Sessões 1-4)
**Data:** 2026-11-15 | **Versão:** 0.5.0-sandbox-web
**Contexto:** Implementação do Sandbox QEMU (Alpine) para validação de código e integração com a Web UI.

---

## 1. O que foi entregue

### 1.1 Sandbox QEMU (Alpine)
- **`QemuDaemon`** (`engine/tools/qemu_daemon.py`):
  - Boot do Alpine via QEMU com `-kernel`, `-initrd`, `-modloop`.
  - Socket TCP persistente (porta 8373) com handshake, login root e `stty -echo`.
  - `bootstrap()` instala `gcc`, `musl-dev`, `python3`, `py3-pip` no tmpfs do Alpine.
  - `run(code, lang="c"|"python")` executa código com isolamento real.
  - Retry automático (3x) no boot e no `apk add` (resiliência a CDN instável).
  - Logs de caixa preta: `serial.log`, `qemu_trace.log`, `daemon.log`.

- **`DiskForge`** (`engine/tools/disk_forge.py`):
  - Criação de `alpine.img.qcow2` para persistência (Sessão 2 adiada).

### 1.2 CodeHook (C e Python)
- **Detecção de C**: `#include` + `int main()` (com fallback para C sem include).
- **Loop de correção**: `gcc` rejeita → prompt de correção com stderr → revalida.
- **A2 Conservadora**: mantém output original, adiciona bloco corrigido (se houver) + aviso honesto.
- **Strip ANSI**: remove códigos CSI e OSC 8 do `gcc`.
- **Passthrough OSL-15**: se daemon offline, retorna output original sem bloquear.

### 1.3 Integração Web
- **Novos eventos de stream** (`engine/api/events.py`):
  - `llm_done`: texto bruto do LLM (antes da validação).
  - `validated`: texto validado/corrigido (`changed: bool`).
- **`WebServer`** (`engine/web/handler.py`):
  - `/sandbox`: endpoint de status (online/offline).
  - `/ask_stream`: agora valida no Alpine se online.
- **Frontend** (`engine/web/static/index.html`):
  - Badge `🟢 sandbox` no header (B2: só aparece se online).
  - Indicador visual `⏳ Validando no Alpine...`.
  - Bloco verde `✅ Corrigido pelo sandbox` (se `changed=True`).
  - `llm_done`/`validated`/`done` no Debug Console.

### 1.4 CLI de Diagnóstico
- `orn sandbox install` — baixa kernel/initramfs/modloop.
- `orn sandbox forge` — cria qcow2 persistente.
- `orn sandbox daemon {start,stop,status,restart}` — gerencia QEMU.
- `orn sandbox bootstrap` — instala pacotes no Alpine.
- `orn sandbox check` — verifica estado do Alpine.
- `orn sandbox test` — valida C.
- `orn sandbox test-python` — valida Python.
- `orn sandbox probe` — mostra caixa preta (logs).
- `orn sandbox doctor` — diagnóstico completo.
- `orn sandbox wipe` — reset do sandbox.

---

## 2. Decisões de Design Travadas

1. **A2 (conservadora)**: usuário vê original + correção. Não perdemos código original.
2. **B2 (badge condicional)**: badge só aparece se daemon online. Sem poluição visual.
3. **Passthrough (OSL-15)**: se daemon offline, hook não bloqueia.
4. **`changed` só é `true`** se o **código** extraído mudou (não só aviso).
5. **Sessão 2 (persistência) adiada**: Alpine netboot `-virt` só tem `squashfs`/`tmpfs`. Migração para ISO fica para F6.x.

---

## 3. Limitações Conhecidas

### 3.1 `orn.dll` — KV cache bug (regressão)
- Segunda request com mesmo prompt recarrega o modelo (~36s).
- **Fix:** recompilar `orn.dll` com `g_history_len = n_tokens` (não `total`).
- **Impacto:** reload de 36s na segunda request. Não afeta correção.

### 3.2 Alpine netboot — sem persistência
- `mount -t ext4` dá `No such device` porque o kernel `netboot -virt` não tem o módulo `ext4`.
- **Fix:** migrar para Alpine ISO (`setup-disk`) em F6.x.
- **Impacto:** `daemon restart` perde `gcc`. `bootstrap` de 3min por sessão.

### 3.3 Qwen 0.5B — limitação em C
- Modelo não corrige `int *arr` (declaração de ponteiro) quando pedido.
- **Fix:** RAG com `doxoade consult` (Sessão 5) injeta exemplos funcionais.
- **Impacto:** `changed=False` em C complexo. Python funciona melhor.

---

## 4. Testes de Validação

| Teste | Status |
|---|---|
| `python -m engine.thinking.code_hook --test` | ✅ 10/10 |
| `orn sandbox test` (C) | ✅ |
| `orn sandbox test-python` (Python) | ✅ |
| `teste_hook_c.py` (loop de correção) | ✅ Mock chamado 2x, corrigido |
| Web UI `bubble sort em C` | ✅ Badge + validação |
| Web UI `função em Python` | ✅ |

---

## 5. Próximos Passos (Sessão 5+)

1. **Recompilar `orn.dll`** (5 min): remove reload de 36s.
2. **RAG com `doxoade consult`** (1 sessão): injeta exemplos de C/Python no prompt. Resolve limitação do 0.5B.
3. **F6.x — Alpine ISO** (1-2 sessões): persistência real, boot ~15s.
4. **F6.1–F6.5** (1 sessão): dívida técnica (`_run_fix` 147 linhas, `__pycache__`, MA'AT falsos positivos).

---

*Documento gerado em 2026-11-15. Base: sessões de implementação do Sandbox QEMU e Web UI.*
