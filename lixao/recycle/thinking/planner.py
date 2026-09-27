# doxoade/thinking/planner.py

class ExecutivePlanner:
    """
    Simula o DLPFC (Dorsolateral Prefrontal Cortex).
    Responsável por manter o objetivo e planejar passos.
    """
    def __init__(self):
        self.working_memory = []
        self.current_goal = None

    def set_goal(self, goal):
        self.current_goal = goal
        self.working_memory = []

    def formulate_strategy(self, context_analysis):
        plan = []
        concepts = [c[0] for c in context_analysis]
        
        # Helper para busca parcial (substring)
        # Permite que 'importerror' ative o gatilho 'error'
        def has_concept(keywords):
            return any(any(k in w for w in concepts) for k in keywords)

        # 1. Lógica DMFC - Detecção de Falha
        if has_concept(['error', 'exception', 'fail', 'crash', 'bug']):
            plan.append("DIAGNOSE_TRACEBACK")
            
            if has_concept(['import', 'module', 'package', 'found']):
                plan.append("CHECK_DEPENDENCIES") # Abdução
            elif has_concept(['syntax', 'indent', 'invalid', 'unexpected']):
                plan.append("FIX_SYNTAX")
            elif has_concept(['assert', 'value', 'type', 'key', 'index']):
                plan.append("ANALYZE_LOGIC")
            else:
                plan.append("SEARCH_KNOWLEDGE_BASE")
                
        # 2. Detecção de Criação
        elif has_concept(['create', 'new', 'generate', 'scaffold', 'make', 'build']):
            plan.append("SCAFFOLD_STRUCTURE")
            plan.append("GENERATE_CODE")
            
        # 3. Detecção de Otimização
        elif has_concept(['slow', 'optimize', 'fast', 'performance', 'memory', 'cpu']):
            plan.append("RUN_PROFILER")
            plan.append("REFACTOR_COMPLEXITY")
            
        # 4. Fallback
        else:
            plan.append("READ_CONTEXT")
            plan.append("EXECUTE_TASK")
            
        return plan