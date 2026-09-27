import json
import os
from collections import defaultdict
from ..tools.filesystem import _find_project_root

class Associator:
    def __init__(self):
        root = _find_project_root()
        self.memory_path = os.path.join(root, ".doxoade", "associative_memory.json")
        self.synapses = defaultdict(dict)
        self.load()

    def learn_association(self, source, target, weight=0.1):
        if source == target: return
        s, t = source.lower(), target.lower()
        current = self.synapses[s].get(t, 0.0)
        new_w = min(1.0, current + weight)
        self.synapses[s][t] = new_w
        self.synapses[t][s] = new_w

    def infer_relations(self, concepts, threshold=0.2):
        activated = defaultdict(float)
        for concept in concepts:
            c = concept.lower()
            activated[c] += 1.0
            if c in self.synapses:
                for neighbor, weight in self.synapses[c].items():
                    if weight > threshold:
                        activated[neighbor] += weight
        sorted_mems = sorted(activated.items(), key=lambda x: x[1], reverse=True)
        return [item for item in sorted_mems[:10]]

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
            with open(self.memory_path, 'w', encoding='utf-8') as f:
                json.dump({k: dict(v) for k, v in self.synapses.items()}, f, indent=2)
        except Exception as e:
            import sys, os
            exc_type, exc_obj, exc_tb = sys.exc_info()
            f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            line_n = exc_tb.tb_lineno
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: save\033[0m")
            print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")

        except Exception as e:
            import sys, os
            exc_type, exc_obj, exc_tb = sys.exc_info()
            f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            line_n = exc_tb.tb_lineno
            print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: save\033[0m")
            print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
            if os.path.exists(self.memory_path):
                try:
                    with open(self.memory_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for k, v in data.items(): self.synapses[k] = v
                except: pass