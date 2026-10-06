# engine/tools/brunnr_terminal.py
"""
Brunnr Terminal — Interface interativa de comandos controlados.
Objetivo: REPL inteligente onde o Brunnr executa, explica, corrige e aprende.
Typhon: onde=engine/tools/, oque=boterminal, quem=brunnr_terminal
quando=Fase 5.3, porquê=interface direta com a IA, origem=orn think + code_sandbox
consequência=se falhar, fallback para orn think via CLI.
"""
import sys
import time
from pathlib import Path

BRUNNR_BANNER = r"""
  ____                      _   _
 | __ ) _ __ _   _ _ __  _ __ | \ | |
 |  _ \| '__| | | | '_ \| '_ \|  \| |
 | |_) | |  | |_| | | | | | | | |\  |
 |____/|_|   \__,_|_| |_|_| |_|_| \_|
  v0.1 — SmolLM2-135M + LoRA PT/EN
  "Colocamos conhecimento na poça."
"""

COMMANDS = {
    "run":     "Executa código Python no sandbox",
    "explain": "Explica conceito de programação",
    "fix":     "Diagnostica e corrige arquivo Python",
    "learn":   "Adiciona conhecimento à poça (memória)",
    "status":  "Mostra estado do modelo e memória",
    "help":    "Lista comandos disponíveis",
    "quit":    "Encerra sessão",
}

class BrunnrTerminal:
    """REPL interativo com comandos controlados."""
    
    def __init__(self, bridge=None):
        self._bridge = bridge
        self._memory_path = Path("data/brunnr_memory.jsonl")
        self._running = False
    
    def start(self) -> None:
        """Inicia o REPL interativo."""
        print(BRUNNR_BANNER)
        print("Digite 'help' para ver comandos, 'quit' para sair.\n")
        self._running = True
        
        while self._running:
            try:
                user_input = input("brunnr> ").strip()
                if not user_input:
                    continue
                
                action, args = self._parse(user_input)
                self._dispatch(action, args)
                
            except KeyboardInterrupt:
                print("\n[INFO] Use 'quit' para sair.")
            except EOFError:
                break
        
        print("\n[INFO] Sessão encerrada. A poça mantém o conhecimento.")
    
    def _parse(self, text: str) -> tuple[str, str]:
        """Extrai ação e argumentos do input."""
        parts = text.split(maxsplit=1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return action, args
    
    def _dispatch(self, action: str, args: str) -> None:
        """Roteia comando para handler correto."""
        handlers = {
            "run":     self._cmd_run,
            "explain": self._cmd_explain,
            "fix":     self._cmd_fix,
            "learn":   self._cmd_learn,
            "status":  self._cmd_status,
            "help":    self._cmd_help,
            "quit":    self._cmd_quit,
            "exit":    self._cmd_quit,
        }
        
        handler = handlers.get(action)
        if handler is None:
            print(f"[ERRO] Comando desconhecido: '{action}'")
            print("       Digite 'help' para ver comandos disponíveis.")
            return
        
        handler(args)
    
    def _cmd_run(self, code: str) -> None:
        """Plano A: Executa código no sandbox isolado."""
        if not code.strip():
            print("[ERRO] Uso: run <código python>")
            return
        
        print(f"[INFO] Executando no sandbox...")
        t0 = time.perf_counter()
        
        try:
            from engine.tools.code_sandbox import stage_code
            import subprocess
            
            path = stage_code(code, stem="brunnr_run")
            result = subprocess.run(
                [sys.executable, "-I", str(path)],
                capture_output=True, text=True, timeout=5
            )
            
            elapsed = time.perf_counter() - t0
            
            if result.stdout:
                print(f"[OUTPUT]\n{result.stdout}")
            if result.stderr:
                print(f"[ERRO]\n{result.stderr}")
            if result.returncode == 0:
                print(f"[OK] Execução concluída em {elapsed:.2f}s")
            else:
                print(f"[FALHA] Código de retorno: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            print("[ERRO] Timeout — possível loop infinito.")
        except Exception as e:
            print(f"[ERRO] {e}")
    
    def _cmd_explain(self, concept: str) -> None:
        """Plano A: Usa o LLM para explicar conceito."""
        if not concept.strip():
            print("[ERRO] Uso: explain <conceito>")
            return
        
        if self._bridge is None:
            print("[ERRO] Bridge não inicializado. Inicie com --model.")
            return
        
        prompt = f"Explique o conceito de '{concept}' em programação. Seja conciso e dê um exemplo prático."
        print(f"[INFO] Consultando Brunnr...")
        
        t0 = time.perf_counter()
        response = self._bridge.ask(prompt, max_tokens=256)
        elapsed = time.perf_counter() - t0
        
        print(f"\n{response}")
        print(f"\n[INFO] {elapsed:.2f}s")
    
    def _cmd_fix(self, filepath: str) -> None:
        """Plano A: Diagnostica arquivo e sugere correção."""
        if not filepath.strip():
            print("[ERRO] Uso: fix <arquivo.py>")
            return
        
        path = Path(filepath)
        if not path.exists():
            print(f"[ERRO] Arquivo não encontrado: {path}")
            return
        
        try:
            from engine.tools.code_sandbox import diagnose_python_file
            issues = diagnose_python_file(path)
            
            if not issues:
                print(f"[OK] {path.name} não tem problemas detectados.")
            else:
                print(f"[DIAG] {len(issues)} problema(s) encontrado(s):")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
        except Exception as e:
            print(f"[ERRO] {e}")
    
    def _cmd_learn(self, data: str) -> None:
        """Plano A: Adiciona conhecimento à poça (append-only)."""
        if not data.strip():
            print("[ERRO] Uso: learn <conhecimento>")
            return
        
        import json
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "type": "user_knowledge",
            "content": data,
            "timestamp": time.time(),
        }
        
        with open(self._memory_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        print(f"[OK] Conhecimento adicionado à poça. ({self._memory_path})")
    
    def _cmd_status(self, args: str) -> None:
        """Mostra estado do modelo e memória."""
        print("[STATUS] Brunnr v0.1")
        print(f"  Modelo: SmolLM2-135M-Instruct + LoRA")
        print(f"  Bridge: {'ativo' if self._bridge else 'inativo'}")
        
        if self._memory_path.exists():
            lines = self._memory_path.read_text(encoding="utf-8").strip().split("\n")
            print(f"  Memória: {len(lines)} entradas na poça")
        else:
            print(f"  Memória: poça vazia")
    
    def _cmd_help(self, args: str) -> None:
        """Lista comandos disponíveis."""
        print("\n[COMANDOS]")
        for cmd, desc in COMMANDS.items():
            print(f"  {cmd:10s} — {desc}")
        print()
    
    def _cmd_quit(self, args: str) -> None:
        """Encerra sessão."""
        self._running = False

if __name__ == "__main__":
    # Inicializar bridge com profile Brunnr
    try:
        from engine.core.llm_bridge import SiCDoxBridge, BridgeConfig
        cfg = BridgeConfig.brunnr_profile()
        bridge = SiCDoxBridge(cfg)
        print("[INFO] Bridge Brunnr inicializado.")
    except Exception as e:
        print(f"[AVISO] Falha ao inicializar bridge: {e}")
        print("[INFO] Comandos 'explain' não funcionarão sem bridge.")
        bridge = None
    
    terminal = BrunnrTerminal(bridge=bridge)
    terminal.start()
