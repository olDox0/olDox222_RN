# alfagold/hive/hive_mind.py
import numpy as np
# [DOX-UNUSED] from colorama import Fore

from ..core.state_packet import StatePacket
from ..core.adaptive_router import AdaptiveRouter
from ..experts.generator_expert import GeneratorExpert
from ..experts.syntax_expert import SyntaxExpert
from ..experts.planning_expert import PlanningExpert
from ..experts.refinement_expert import RefinementExpert
from ..experts.reward_expert import RewardExpert

class HiveMindMoE:
    """
    Cérebro Central (Orquestrador MoE).
    Coordena: Generator (Wernicke), Syntax (Broca), Planner (Frontal),
    Router (Tálamo) e Refinement (Cerebelo).
    """
    def __init__(self):
        self.generator = GeneratorExpert()
        
        self.syntax = SyntaxExpert(self.generator.model.tokenizer)
        self.planner = PlanningExpert(
            d_model=self.generator.model.d_model,
            vocab_size=len(self.generator.model.tokenizer.vocab)
        )
        self.cerebellum = RefinementExpert()
        self.rewarder = RewardExpert(self.generator.model.tokenizer)
        
        self.router = AdaptiveRouter(d_model=self.generator.model.d_model, num_clusters=3)
        
        # Cache de IDs
        def safe_get_id(text):
            ids = self.generator.model.tokenizer.encode(text)
            return ids[0] if ids else -1

        self.id_space = safe_get_id(" ")

    def generate_step(self, packet: StatePacket, temp=0.7):
        # 1. GERAÇÃO
        packet = self.generator.process(packet)
        
        # 2. PLANEJAMENTO
        packet.syntax_state = self.syntax.estado
        packet = self.planner.process(packet)
        
        # 3. ROTEAMENTO
        if packet.embedding_vector is not None:
            self.router.route(packet.embedding_vector, training=False)

        # 4. INIBIÇÃO
        final_logits = packet.logits.copy()
        mask = self.syntax.get_inhibition_mask(final_logits.shape[0])
        packet.inhibition_mask = mask
        final_logits += mask
        
        # 5. DECISÃO
        scaled_logits = np.clip(final_logits / temp, -50, 50)
        exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
        probs = exp_logits / np.sum(exp_logits)
        
        next_id = None
        
        # Amostragem com Validação
        for _ in range(10):
            cand_id = int(np.random.choice(len(probs), p=probs))
            
            # [FIX] Decodifica RAW (sem strip)
            raw_token = self.generator.decode(cand_id)
            clean_token = raw_token.strip()
            
            # Se for só espaço, considera válido para o Arquiteto (ele ignora)
            if not clean_token: 
                next_id = cand_id
                break
                
            valido, _ = self.syntax.validar(clean_token)
            if valido:
                next_id = cand_id
                # Atualiza estado do Arquiteto com token limpo
                self.syntax.observe(clean_token)
                break
            else:
                probs[cand_id] = 0
                s = np.sum(probs)
                if s > 0: probs /= s
                else: break
        
        # Fallback
        if next_id is None:
            sug = self.syntax.sugerir_correcao()
            if sug:
                sug_ids = self.generator.model.tokenizer.encode(sug)
                if sug_ids: 
                    next_id = sug_ids[0]
                    self.syntax.observe(sug)
        
        # Fallback Final
        if next_id is None:
            next_id = int(np.argmax(final_logits))
            raw_token = self.generator.decode(next_id)
            self.syntax.observe(raw_token.strip())
            
        # 6. FEEDBACK
        packet.token_ids.append(next_id)
        
        # [FIX] Retorna o token bruto (com espaços) para o texto final
        raw_token = self.generator.decode(next_id)
        packet.generated_token = raw_token
        
        return packet, raw_token

    def run_sequence(self, prompt, length=50):
        packet = StatePacket(input_text=prompt)
        print(f"🧠 [HiveMoE] Prompt: {prompt}")
        
        input_ids = self.generator.model.tokenizer.encode(prompt)
        packet.token_ids = list(input_ids)
        
        self.syntax.reset()
        for tid in input_ids:
            t_str = self.generator.decode(tid).strip()
            if t_str: self.syntax.observe(t_str)
            
        full_text = ""
        
        for _ in range(length):
            packet, token = self.generate_step(packet)
            
            if "ENDMARKER" in token: 
                if self.syntax.estado == "CORPO": break
            
            print(".", end="", flush=True)
            full_text += token
            
        print("\n✅ Concluído.")
        return full_text