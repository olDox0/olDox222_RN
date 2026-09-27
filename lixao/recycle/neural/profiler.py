"""
NEURAL PROFILER v2.1 (Safe Mode).
Tratamento de exceção para conflitos de profiling e relatórios detalhados.
"""
import cProfile
import pstats
import io
# [DOX-UNUSED] import os
from pstats import SortKey
from colorama import Fore, Style

class NeuralProfiler:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.pr = cProfile.Profile() if enabled else None

    def __enter__(self):
        if self.enabled:
            try:
                self.pr.enable()
            except ValueError:
                # Se já existe um profiler rodando (ex: IDE ou wrapper), não quebra.
                print(Fore.YELLOW + "   ⚠️ [CRONOS] Profiler global já ativo. Ignorando perfilamento local." + Style.RESET_ALL)
                self.enabled = False 
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.enabled:
            self.pr.disable()
            self._gerar_relatorio_detalhado()

    def _gerar_relatorio_detalhado(self):
        s = io.StringIO()
        ps = pstats.Stats(self.pr, stream=s).sort_stats(SortKey.CUMULATIVE)
        
        print(Fore.CYAN + "\n" + "="*60)
        print("📊 RELATÓRIO DE PERFORMANCE (CRONOS v2.0)")
        print("="*60 + Style.RESET_ALL)
        
        # Top 20 funções
        ps.print_stats(20)
        
        total_calls = ps.total_calls
        total_time = ps.total_tt
        
        print(f"Total de Chamadas: {total_calls}")
        print(f"Tempo Total de CPU: {total_time:.4f}s")
        
        print(Fore.CYAN + "\n🔍 DIAGNÓSTICO DE GARGALOS:" + Style.RESET_ALL)
        
        output = s.getvalue()
        gargalos = []
        
        # Detecção de Math Lookup (Novo na v16)
        if "fast_exp" in output:
             gargalos.append((Fore.GREEN + "[OTIMIZADO] Math Lookup", "Tabela de exponenciais está sendo usada."))

        if "dot" in output or "matmul" in output:
            gargalos.append((Fore.RED + "[CRÍTICO] Álgebra Linear", "CPU saturada com multiplicação de matrizes."))
        
        if "method 'reduce' of 'numpy.ufunc'" in output:
            gargalos.append((Fore.YELLOW + "[ALTO] Reduções NumPy", "Muitas operações de soma/max (Softmax/Loss)."))
            
        if "built-in method io.open" in output:
             gargalos.append((Fore.MAGENTA + "[I/O] Acesso a Disco", "Leitura/Escrita de arquivos lenta."))

        if not gargalos:
            print("   ✅ Distribuição equilibrada (ou o treino foi muito rápido).")
        else:
            for titulo, desc in gargalos:
                print(f"   {titulo}: {desc}")

        print(Fore.CYAN + "="*60 + Style.RESET_ALL)