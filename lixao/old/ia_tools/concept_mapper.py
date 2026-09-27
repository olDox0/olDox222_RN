# ia_tools/concept_mapper.py
import ast
import json
import os
from typing import Dict, Any

class ConceptMapper:
    def __init__(self):
        # L0: Ontologia Python Expandida (IDs 0-1000)
        self.l0_concepts = {
            "Module": 1, "ClassDef": 2, "FunctionDef": 3,
            "Assign": 5, "Attribute": 6, "Call": 7,
            "If": 10, "For": 11, "While": 12,
            "Return": 20, "Raise": 21,
            "Compare": 30, "BinOp": 31, "BoolOp": 32,
            "Name": 60, "Expr": 90, "Constant": 91
        }
        self.id_counter = 2001 # OIA Flexible IDs (2001+)

    def internalizar(self, code_path: str) -> Dict[str, Any]:
        """Transforma arquivo Python em Grafo de Intencionalidade."""
        with open(code_path, "r", encoding="utf-8") as f:
            root_node = ast.parse(f.read())
        
        return self._walk(root_node)

    def _walk(self, node: ast.AST) -> Dict[str, Any]:
        node_type = type(node).__name__
        cid = self.l0_concepts.get(node_type, 999)
        
        data = {
            "id": cid,
            "type": node_type,
            "flow": []
        }

        # L1: Mapeamento de Assinaturas e Funções
        if isinstance(node, ast.FunctionDef):
            data["oia_id"] = self.id_counter
            data["label"] = f"CAPACITY:{node.name}"
            self.id_counter += 1

        # L2: Mapeamento de Lógica de Fluxo (Causalidade)
        for child in ast.iter_child_nodes(node):
            res = self._walk(child)
            if res: data["flow"].append(res)
            
        return data

if __name__ == "__main__":
    mapper = ConceptMapper()
    # Alvo: A Semente Sagrada (Arquiteto v20)
    graph = mapper.internalizar("recycle/logic.py")
    with open("ia_tools/seed_graph.json", "w") as f:
        json.dump(graph, f, indent=2)
    print(f"🧬 [OIA] Semente 'validar' mapeada em ia_tools/seed_graph.json")