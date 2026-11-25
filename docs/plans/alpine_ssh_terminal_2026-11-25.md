# Terminal SSH do Alpine/QEMU

Branch de implementação: `feature/alpine-ssh-terminal`  
Base de integração: `linux-alpine-sicdox-bridge`

## Objetivo

Disponibilizar um terminal Linux interativo no Alpine persistente a partir do Windows, sem usar o parser de comandos do CMD para enviar scripts multilinha pela serial.

O terminal usa o cliente OpenSSH do Windows e um TTY real no guest. O canal serial existente continua reservado ao controle e à automação do ORN.

## Arquitetura

- QEMU mantém a rede user-mode/NAT existente.
- QEMU encaminha `127.0.0.1:<ORN_QEMU_SSH_PORT>` para a porta TCP 22 do guest.
- Porta padrão do host: 2222; pode ser alterada por `ORN_QEMU_SSH_PORT`.
- Alpine instala `openssh-server` e o serviço OpenRC correspondente sob demanda.
- O Windows gera uma chave Ed25519 dedicada em `data/sandbox/ssh/`.
- A chave pública é instalada em `/root/.ssh/authorized_keys`.
- SSH aceita somente autenticação por chave para root; senha e keyboard-interactive são desabilitados.
- A primeira conexão usa TOFU por `StrictHostKeyChecking=accept-new`; alterações posteriores na chave de host são recusadas.

## Uso

Requisitos Windows: OpenSSH Client, incluindo `ssh.exe` e `ssh-keygen.exe`.

```cmd
where ssh
where ssh-keygen
ssh -V
```

Depois de atualizar o código e garantir que não há uma VM antiga sem host forwarding:

```cmd
orn sandbox daemon restart
orn sandbox terminal
```

O comando inicia o daemon se estiver offline, cria/reutiliza a chave Ed25519, confirma a porta, instala/configura sshd de forma idempotente e abre a sessão SSH com TTY. Digite `exit` ou Ctrl+D para sair; o QEMU permanece ativo.

## Segurança

- O host forwarding é vinculado exclusivamente a `127.0.0.1`, não à LAN.
- A chave privada permanece no Windows em `data/sandbox/ssh/id_ed25519`.
- A chave pública é adicionada idempotentemente ao guest.
- `PermitRootLogin prohibit-password`, `PasswordAuthentication no` e `KbdInteractiveAuthentication no` são configurados.
- A chave de host fica no `known_hosts` dedicado do ORN. Se ela mudar inesperadamente, verifique o guest antes de apagar a entrada.

## Transferência de arquivos

A implementação inicial entrega somente terminal interativo. A mesma rota SSH permitirá adicionar `scp` posteriormente sem modificar o canal serial.

## Testes

```cmd
python -m pytest tests/test_qemu_ssh_terminal.py -q
python -m pytest tests/test_alpine_llm_bridge.py tests/test_kv_cache_options.py -q
```

Os testes cobrem validação de porta, binding em loopback, geração de chave, script de provisionamento, detecção da porta e registro do comando Click. Não iniciam QEMU nem instalam sshd real; o teste de integração manual deve ser executado no guest persistente atualizado.
