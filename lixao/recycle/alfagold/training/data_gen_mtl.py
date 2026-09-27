# alfagold/training/data_gen_mtl.py
import random

# Fases: 0:INICIO, 1:NOME, 2:ARGS, 3:TRANSICAO, 4:CORPO
PHASES = {"INICIO":0, "NOME":1, "ARGS":2, "TRANSICAO":3, "CORPO":4}

def generate_mtl_data(count=2000):
    dataset = []
    
    for _ in range(count):
        mode = random.choice(["math", "io", "logic"])
        tokens = []
        phases = []
        
        # --- ASSINATURA COMUM ---
        tokens.append("def"); phases.append(PHASES["INICIO"])
        
        if mode == "math":
            fname = random.choice(["soma", "calc", "dobro"])
            arg1 = "a"; arg2 = "b"
        elif mode == "io":
            fname = random.choice(["salvar", "ler", "logar"])
            arg1 = "file"; arg2 = "data"
        else:
            fname = random.choice(["check", "validar", "testar"])
            arg1 = "val"; arg2 = "limit"
            
        tokens.append(fname); phases.append(PHASES["NOME"])
        tokens.append("("); phases.append(PHASES["ARGS"])
        tokens.append(arg1); phases.append(PHASES["ARGS"])
        tokens.append(","); phases.append(PHASES["ARGS"])
        tokens.append(arg2); phases.append(PHASES["ARGS"])
        tokens.append(")"); phases.append(PHASES["ARGS"])
        tokens.append(":"); phases.append(PHASES["TRANSICAO"])
        
        # --- CORPO VARIÁVEL ---
        if mode == "math":
            tokens.append("return"); phases.append(PHASES["CORPO"])
            tokens.append(arg1); phases.append(PHASES["CORPO"])
            tokens.append("+"); phases.append(PHASES["CORPO"])
            tokens.append(arg2); phases.append(PHASES["CORPO"])
            
        elif mode == "io":
            tokens.append("with"); phases.append(PHASES["CORPO"])
            tokens.append("open"); phases.append(PHASES["CORPO"])
            tokens.append("("); phases.append(PHASES["CORPO"])
            tokens.append(arg1); phases.append(PHASES["CORPO"])
            tokens.append(","); phases.append(PHASES["CORPO"])
            tokens.append("'w'"); phases.append(PHASES["CORPO"])
            tokens.append(")"); phases.append(PHASES["CORPO"])
            tokens.append("as"); phases.append(PHASES["CORPO"])
            tokens.append("f"); phases.append(PHASES["CORPO"])
            tokens.append(":"); phases.append(PHASES["CORPO"])
            tokens.append("f"); phases.append(PHASES["CORPO"])
            tokens.append("."); phases.append(PHASES["CORPO"])
            tokens.append("write"); phases.append(PHASES["CORPO"])
            tokens.append("("); phases.append(PHASES["CORPO"])
            tokens.append(arg2); phases.append(PHASES["CORPO"])
            tokens.append(")"); phases.append(PHASES["CORPO"])
            
        elif mode == "logic":
            tokens.append("if"); phases.append(PHASES["CORPO"])
            tokens.append(arg1); phases.append(PHASES["CORPO"])
            tokens.append(">"); phases.append(PHASES["CORPO"])
            tokens.append(arg2); phases.append(PHASES["CORPO"])
            tokens.append(":"); phases.append(PHASES["CORPO"])
            tokens.append("return"); phases.append(PHASES["CORPO"])
            tokens.append("True"); phases.append(PHASES["CORPO"])
            
        full_text = " ".join(tokens)
        dataset.append((full_text, phases))
        
    return dataset