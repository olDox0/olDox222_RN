import re
from .associator import Associator
from .planner import ExecutivePlanner

class ThinkingCore:
    def __init__(self):
        self.associator = Associator()
        self.planner = ExecutivePlanner()

    def process_thought(self, user_input, file_context=None):
        # 1. Atenção (Extração)
        raw_concepts = self._tokenize(user_input)
        if file_context:
            raw_concepts.extend(self._tokenize(file_context)[:10])

        # 2. Associação (Parietal)
        expanded_context = self.associator.infer_relations(raw_concepts)
        
        # 3. Planejamento (Frontal)
        self.planner.set_goal(user_input)
        strategy = self.planner.formulate_strategy(expanded_context)
        
        # 4. Aprendizado (Consolidação)
        u_concepts = list(set(raw_concepts))
        for i in range(len(u_concepts)):
            for j in range(i + 1, len(u_concepts)):
                self.associator.learn_association(u_concepts[i], u_concepts[j])
        self.associator.save()

        return {
            "focus": raw_concepts,
            "associations": [x[0] for x in expanded_context],
            "plan": strategy
        }

    def _tokenize(self, text):
        if not text: return []
        ignore = {'the', 'a', 'is', 'in', 'to', 'for', 'of', 'and', 'with', 'def', 'class'}
        clean = re.sub(r'[^a-zA-Z0-9_]', ' ', text.lower())
        return [w for w in clean.split() if len(w) > 2 and w not in ignore]