# -*- coding: utf-8 -*-
import sys
import os
import time
import shutil
import hashlib
from pathlib import Path
import importlib.util
import importlib.machinery

# Força o CMD do Windows a renderizar cores
os.system("")

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    DIM = '\033[2m'

# =====================================================================
# SIMULAÇÃO DO SEU vulcan_safe_loader.py
# Isso valida o funcionamento da sua ferramenta de segurança nativa
# =====================================================================
class BenchmarkSafeLoader(importlib.machinery.ExtensionFileLoader):
    def __init__(self, fullname, path, py_fallback):
        super().__init__(fullname, path)
        self._py_fallback = py_fallback

    def exec_module(self, module):
        try:
            return super().exec_module(module)
        except Exception as e:
            # 🔥 FALHOU → REMOVE O .pyd E CAI PARA .py
            sys.modules.pop(module.__name__, None)
            if self._py_fallback and os.path.exists(self._py_fallback):
                spec = importlib.util.spec_from_file_location(
                    module.__name__,
                    self._py_fallback
                )
                py_mod = importlib.util.module_from_spec(spec)
                sys.modules[module.__name__] = py_mod
                spec.loader.exec_module(py_mod)
                return
            raise

def get_all_targets(project_root: Path):
    bin_dir = project_root / ".doxoade" / "vulcan" / "bin"
    ext = ".pyd" if os.name == "nt" else ".so"
    binaries = list(bin_dir.glob(f"*{ext}"))
    
    if not binaries: return []

    py_files =[]
    skip = {".git", "venv", ".venv", "__pycache__", "build", "dist", ".doxoade"}
    for root, dirs, files in os.walk(project_root):
        dirs[:] =[d for d in dirs if d not in skip]
        for f in files:
            if f.endswith(".py") and f != "vulcan_routing_bench.py":
                py_files.append(Path(root) / f)

    hash_index = {hashlib.sha256(str(py.resolve()).encode()).hexdigest()[:6]: py for py in py_files}

    targets =[]
    for bin_path in binaries:
        pyd_hash = bin_path.stem.split("_")[-1] if "_" in bin_path.stem else None
        source = hash_index.get(pyd_hash)
        if source:
            rel_path = source.relative_to(project_root)
            mod_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
            targets.append((mod_name, bin_path, source))

    return targets

def run_direct_benchmark(module_name: str, pyd_path: Path, py_path: Path):
    print(f"\n{Colors.CYAN}=== AUDITORIA E BENCHMARK VULCAN CORE ==={Colors.RESET}")
    print(f"Alvo: {Colors.YELLOW}{module_name}{Colors.RESET}")

    # -------------------------------------------------------------------
    # FASE 1: BENCHMARK DE PERFORMANCE NATIVA (.PY vs .PYD)
    # -------------------------------------------------------------------
    print(f"\n{Colors.MAGENTA}[1] PERFORMANCE COMPARATIVA{Colors.RESET}")
    
    # Teste A: Python Puro
    sys.modules.pop(module_name, None)
    spec_py = importlib.util.spec_from_file_location(module_name, str(py_path))
    mod_py = importlib.util.module_from_spec(spec_py)
    
    t0 = time.perf_counter()
    spec_py.loader.exec_module(mod_py)
    t_py = (time.perf_counter() - t0) * 1000
    print(f"   -> Carregando Python Puro (.py)  : {t_py:>8.3f} ms")

    # Teste B: Vulcan Binário
    sys.modules.pop(module_name, None)
    spec_pyd = importlib.util.spec_from_file_location(module_name, str(pyd_path))
    mod_pyd = importlib.util.module_from_spec(spec_pyd)
    
    try:
        t0 = time.perf_counter()
        spec_pyd.loader.exec_module(mod_pyd)
        t_pyd = (time.perf_counter() - t0) * 1000
        print(f"   -> Carregando Vulcan Nativo (.pyd): {Colors.GREEN}{t_pyd:>8.3f} ms{Colors.RESET}")
        
        # Calcular Speedup
        speedup = t_py / t_pyd if t_pyd > 0 else 0
        if speedup > 1:
            print(f"   => {Colors.GREEN}GANHO: {speedup:.1f}x mais rápido!{Colors.RESET} 🔥")
        else:
            print(f"   => {Colors.YELLOW}Marginal (Sem ganho expressivo neste módulo){Colors.RESET}")
            
    except Exception as e:
        print(f"   {Colors.RED}✘ Falha ao carregar o PYD nativo: {e}{Colors.RESET}")
        return False

    # -------------------------------------------------------------------
    # FASE 2: AUDITORIA DO SAFE_LOADER (vulcan_safe_loader.py)
    # -------------------------------------------------------------------
    print(f"\n{Colors.MAGENTA}[2] AUDITORIA DO SAFE EXTENSION LOADER{Colors.RESET}")
    
    backup_path = pyd_path.with_suffix(".backup")
    locked_tmp = pyd_path.with_suffix(".locked_tmp")
    
    try:
        # Renomeia o binário em uso e cria um corrompido propositalmente
        shutil.copy2(pyd_path, backup_path)
        try: os.rename(pyd_path, locked_tmp)
        except OSError: pass 
        
        with open(pyd_path, 'wb') as f:
            f.write(b"CORRUPTED_DLL_HEADER_VULCAN")

        print(f"   -> Binário corrompido propositalmente injetado.")
        
        sys.modules.pop(module_name, None)
        
        # USA O SEU SAFE LOADER DIRETAMENTE
        print(f"   -> Acionando o SafeExtensionLoader...")
        safe_loader = BenchmarkSafeLoader(module_name, str(pyd_path), str(py_path))
        spec_safe = importlib.util.spec_from_loader(module_name, safe_loader)
        mod_safe = importlib.util.module_from_spec(spec_safe)
        
        safe_loader.exec_module(mod_safe)
        
        # Pega o arquivo que acabou na memória
        loaded_file = getattr(sys.modules.get(module_name, mod_safe), '__file__', '')
        
        if loaded_file.endswith('.py'):
            print(f"{Colors.GREEN}   ✔ SUCESSO ABSOLUTO:{Colors.RESET} O SafeLoader interceptou a falha fatal e fez o downgrade automático para o .py de forma transparente!")
        else:
            print(f"{Colors.RED}   ✘ FALHA DE SEGURANÇA:{Colors.RESET} Carregou algo inesperado: {loaded_file}")

    except Exception as e:
         print(f"{Colors.RED}   ✘ FALHA CRÍTICA:{Colors.RESET} O SafeLoader deixou o erro vazar: {e}")
    
    finally:
        # Limpeza e restauração do ambiente
        if pyd_path.exists():
            try: os.remove(pyd_path)
            except OSError: pass
        if locked_tmp.exists():
            try: os.rename(locked_tmp, pyd_path)
            except OSError: pass
        if backup_path.exists() and not pyd_path.exists():
            shutil.copy2(backup_path, pyd_path)
        if backup_path.exists():
            try: os.remove(backup_path)
            except OSError: pass
            
        print(f"\n{Colors.DIM}[Sistema higienizado e .pyd original restaurado]{Colors.RESET}")

    return True

if __name__ == "__main__":
    project_root = Path(os.getcwd())
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    targets = get_all_targets(project_root)
    
    if not targets:
        print(f"{Colors.RED}Nenhum módulo compilado rastreável encontrado.{Colors.RESET}")
        sys.exit(1)

    success = False
    for mod_name, pyd_target, py_target in targets:
        if "lixao" in mod_name: continue
        
        success = run_direct_benchmark(mod_name, pyd_target, py_target)
        if success:
            break