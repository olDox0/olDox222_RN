# ia_core/executive.py
from .llm_bridge import SiCDoxBridge
from .blackboard import DoxoBoard
from .logic_filter import SiCDoxValidator # Novo!

class SiCDoxExecutive:
    def __init__(self, model_path: str):
        self.bridge = SiCDoxBridge(model_path)
        self.board = DoxoBoard()
        self.validator = SiCDoxValidator()

    def process_goal(self, goal: str):
        print(f"🎯 Meta: {goal}")
        tentativas = 0
        
        try:
            while tentativas < 3:
                tentativas += 1
                proposal = self.bridge.ask_sicdox(goal)
                
                # Validação via System 2
                aprovado, motivo = self.validator.validar_output(proposal)
                
                if aprovado:
                    h_id = self.board.post_hypothesis("Qwen-Coder", proposal)
                    self.board.add_causal_link("USER_GOAL", h_id, "VALIDATED_PLAN")
                    return proposal, self.board.get_summary()
                else:
                    print(f"⚠️ [VETO] Tentativa {tentativas} rejeitada: {motivo}")
                    # Refina o objetivo para a próxima tentativa
                    goal = f"{goal} (Lembre-se: Use apenas Python e o padrão Chief-Gold do Doxoade)"
        finally:
            # GARANTIA GOLD: Limpeza de memória imediata
            self.bridge.shutdown()
        
        return "Falha ao gerar plano válido.", self.board.get_summary()