# engine/runtime/brunnr_terminal.py
"""
Brunnr Boterminal — Interface de comandos controlados para a IA.
Objetivo: Prover um REPL estruturado onde o usuário dá comandos
e Brunnr executa ações específicas (não chat livre).
Typhon: onde=engine/runtime/, oque=boterminal, quem=brunnr_terminal
quando=Fase 5, porquê=controle preciso sobre a IA, origem=CLI do ORN
consequência=se falhar, fallback para orn think (chat livre).

Filosofia: "A gente coloca água (conhecimento) nela."
Cada comando é um balde. Cada resposta é um reflexo.
"""
import sys
import time
from pathlib import Path
from typing import Optional

# Comandos disponíveis
COMMANDS = {
    "/code": "Gera código Python a partir de uma descrição",
    "/explain": "Explica um conceito técnico em PT/EN",
    "/translate": "Traduz termo técnico (pt↔en)",
    "/debug": "Analisa código e sugere correções",
    "/glossary": "Busca no glossário técnico PT↔EN",
    "/train": "Gerencia treinamento LoRA (status/run)",
    "/model": "Info ou troca de modelo (info/switch)",
    "/help": "Lista todos os comandos disponíveis",
    "/quit": "Sai do Boterminal Brunnr",
}

BANNER = """
╔══════════════════════════════════════════════════════════╗
║  🌊 BRUNNR — A Poça de Conhecimento                     ║
║  "A gente coloca água (conhecimento) nela."              ║
║                                                          ║
║  Digite /help para ver os comandos disponíveis.          ║
║  Digite /quit para sair.                                 ║
╚══════════════════════════════════════════════════════════╝
"""

def parse_command(user_input: str) -> tuple[str, str]:
    """Parseia a entrada do usuário em (comando, argumentos)."""
    user_input = user_input.strip()
    if not user_input:
        return ("", "")
    
    parts = user_input.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    return (cmd, args)

def handle_help(args: str) -> None:
    """Exibe lista de comandos."""
    print("\n  Comandos disponíveis:\n")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:15s} {desc}")
    print()

def handle_code(args: str) -> None:
    """Gera código Python via Brunnr."""
    if not args:
        print("  [Brunnr] Uso: /code <descrição da função>")
        return
    
    print(f"  [Brunnr] 🌊 Gerando código para: {args}")
    
    try:
        from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
        
        cfg = BridgeConfig.smol_profile()
        # Ajustes para SmolLM 135M
        cfg.max_tokens = 512        # Era 8192 → reduz para evitar alucinação
        cfg.temperature = 0.3       # Era 0.5 → mais determinístico
        cfg.top_p = 0.85            # Mais focado
        cfg.repeat_penalty = 1.3    # Evita repetição
        
        bridge = SiCDoxBridge(cfg)
        
        # Template otimizado para SmolLM
        prompt = (
            f"# Tarefa: {args}\n"
            f"# Gere apenas código Python válido, sem explicações.\n"
            f"# Envolva o código em ```python ... ```\n\n"
        )
        
        result = bridge.ask(prompt, max_tokens=cfg.max_tokens)
        
        if result:
            print(f"\n{result}")
        else:
            print("  [Brunnr] ⚠ Sem resposta do modelo.")
            
    except Exception as e:
        print(f"  [Brunnr] ⚠ Erro na inferência: {e}")

def handle_explain(args: str) -> None:
    """Explica conceito técnico."""
    if not args:
        print("  [Brunnr] Uso: /explain <conceito>")
        return
    
    print(f"  [Brunnr] 🌊 Explicando: {args}")
    
    try:
        from engine.core.llm_bridge import BridgeConfig, SiCDoxBridge
        
        cfg = BridgeConfig.smol_profile()
        bridge = SiCDoxBridge(cfg)
        
        prompt = (
            f"# Explique o conceito de {args} em programação Python.\n"
            f"# Explain the concept of {args} in Python programming.\n\n"
        )
        
        # FIX: bridge.ask() retorna string
        result = bridge.ask(prompt, max_tokens=256)
        
        if result:
            print(f"\n{result}")
        else:
            print("  [Brunnr] ⚠ Sem resposta do modelo.")
            
    except Exception as e:
        print(f"  [Brunnr] ⚠ Erro: {e}")

def handle_glossary(args: str) -> None:
    """Busca no glossário PT↔EN."""
    GLOSSARY = {
        "recursão": "recursion", "recursion": "recursão",
        "lista": "list", "list": "lista",
        "dicionário": "dictionary", "dictionary": "dicionário",
        "tupla": "tuple", "tuple": "tupla",
        "conjunto": "set", "set": "conjunto",
        "laço": "loop", "loop": "laço",
        "função": "function", "function": "função",
        "classe": "class", "class": "classe",
        "herança": "inheritance", "inheritance": "herança",
        "polimorfismo": "polymorphism", "polymorphism": "polimorfismo",
        "encapsulamento": "encapsulation", "encapsulation": "encapsulamento",
        "decorador": "decorator", "decorator": "decorador",
        "gerador": "generator", "generator": "gerador",
        "iterador": "iterator", "iterator": "iterador",
        "exceção": "exception", "exception": "exceção",
        "módulo": "module", "module": "módulo",
        "pacote": "package", "package": "pacote",
        "escopo": "scope", "scope": "escopo",
        "closure": "closure", "compreensão de lista": "list comprehension",
        "list comprehension": "compreensão de lista",
        "ordenação": "sorting", "sorting": "ordenação",
        "busca binária": "binary search", "binary search": "busca binária",
        "pilha": "stack", "stack": "pilha",
        "fila": "queue", "queue": "fila",
    }
    
    if not args:
        print("  [Brunnr] Uso: /glossary <termo>")
        return
    
    term = args.lower().strip()
    if term in GLOSSARY:
        print(f"  [Brunnr] 🌊 {args} = {GLOSSARY[term]}")
    else:
        print(f"  [Brunnr] ⚠ Termo '{args}' não encontrado no glossário.")
        print(f"  [Brunnr] 💡 Termos disponíveis: {', '.join(sorted(set(GLOSSARY.values())))[:100]}...")

def handle_train(args: str) -> None:
    """Gerencia treinamento LoRA."""
    subcmd = args.split()[0] if args else "status"
    
    if subcmd == "status":
        adapter = Path("data/training/lora_adapter_peft")
        dataset = Path("data/training/brunnr_full.jsonl")
        
        print("  [Brunnr] 🌊 Status do Treinamento:")
        print(f"    Adapter: {'✔ Existe' if adapter.exists() else '✘ Não encontrado'}")
        if adapter.exists():
            size = sum(f.stat().st_size for f in adapter.rglob("*") if f.is_file())
            print(f"    Tamanho: {size / 1024:.1f} KB")
        
        print(f"    Dataset: {'✔ Existe' if dataset.exists() else '✘ Não encontrado'}")
        if dataset.exists():
            lines = sum(1 for _ in open(dataset))
            print(f"    Amostras: {lines}")
    
    elif subcmd == "run":
        print("  [Brunnr] 🌊 Iniciando treinamento LoRA...")
        print("  [Brunnr] 💡 Use: python engine/training/lora_trainer.py")
    
    else:
        print("  [Brunnr] Uso: /train [status|run]")

def handle_model(args: str) -> None:
    """Info ou troca de modelo."""
    subcmd = args.split()[0] if args else "info"
    
    if subcmd == "info":
        from engine.core.llm_bridge import BridgeConfig
        cfg = BridgeConfig.smol_profile()
        print("  [Brunnr] 🌊 Modelo Ativo:")
        print(f"    Nome: {cfg.model_path.name}")
        print(f"    Caminho: {cfg.model_path}")
        print(f"    Existe: {'✔' if cfg.model_path.exists() else '✘'}")
        print(f"    n_ctx: {cfg.n_ctx}")
        print(f"    threads: {cfg.n_threads}")
    else:
        print("  [Brunnr] Uso: /model [info|switch <nome>]")

def run_boterminal():
    """Loop principal do Boterminal Brunnr."""
    print(BANNER)
    
    handlers = {
        "/help": handle_help,
        "/code": handle_code,
        "/explain": handle_explain,
        "/glossary": handle_glossary,
        "/train": handle_train,
        "/model": handle_model,
    }
    
    while True:
        try:
            user_input = input("brunnr> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  [Brunnr] 🌊 Até logo!")
            break
        
        if not user_input:
            continue
        
        cmd, args = parse_command(user_input)
        
        if cmd == "/quit":
            print("  [Brunnr] 🌊 Até logo!")
            break
        elif cmd in handlers:
            handlers[cmd](args)
        elif cmd.startswith("/"):
            print(f"  [Brunnr] ⚠ Comando desconhecido: {cmd}")
            print("  [Brunnr] 💡 Digite /help para ver os comandos.")
        else:
            # Entrada sem comando = trata como /code
            print(f"  [Brunnr] 💡 Dica: Use /code {user_input}")

if __name__ == "__main__":
    run_boterminal()
