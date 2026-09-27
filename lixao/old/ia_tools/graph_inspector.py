# ia_tools/graph_inspector.py
import json
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

class GraphInspector:
    def __init__(self):
        self.console = Console()

    def render_flow(self, data: dict, tree: Tree = None):
        label = data.get("label", f"{data['type']}_{data['id']}")
        cid = data['id']
        
        # Esquema de Cores Chief-Gold
        color = "white"
        if "CAPACITY" in label: color = "cyan"
        elif cid == 10: color = "yellow"    # IF
        elif cid in [20, 21]: color = "red" # Saídas (Return/Raise)
        elif cid == 999: color = "bright_black" # Desconhecido (Dim)

        content = f"[{color}]{label}[/{color}]"
        
        if tree is None:
            tree = Tree(Panel.fit(content, title="SiCDox Reasoning Flow"))
        else:
            # PASC-5.1: Brevidade. Só ramifica se for um nó de controle ou função.
            tree = tree.add(content)

        for child in data.get("flow", []):
            # Mostramos nós de controle, funções e o que for identificado (não 999)
            if child['id'] != 999 or child['type'] in ["Assign", "ClassDef"]:
                self.render_flow(child, tree)
        
        return tree

    def show(self, file_path: str):
        with open(file_path, "r") as f:
            data = json.load(f)
        flow_tree = self.render_flow(data)
        self.console.print(flow_tree)

if __name__ == "__main__":
    inspector = GraphInspector()
    inspector.show("ia_tools/seed_graph.json")