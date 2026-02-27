"""
AST ENCODER
Extrai a estrutura lógica e semântica do código para alimentar a IA.
"""
import ast

class CodeAnalyzer:
    def extract_features(self, code_snippet):
        """
        Analisa um trecho de código e retorna metadados estruturais.
        """
        try:
            tree = ast.parse(code_snippet)
        except SyntaxError:
            return {"type": "BROKEN", "features": []}

        features = []
        docstring = ""
        func_name = ""
        
        for node in ast.walk(tree):
            # 1. Identificar o Tipo de Estrutura
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                docstring = ast.get_docstring(node) or ""
                features.append("DEF")
                
            # 2. Identificar Operações Críticas
            elif isinstance(node, ast.Return): features.append("RETURN")
            elif isinstance(node, ast.If): features.append("LOGIC_BRANCH")
            elif isinstance(node, ast.For) or isinstance(node, ast.While): features.append("LOOP")
            elif isinstance(node, ast.Try): features.append("ERROR_HANDLING")
            
            # 3. Identificar Domínio (Chamadas de API)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                    if name in ['print', 'log']: features.append("IO_OP")
                    if name in ['open', 'read', 'write']: features.append("FILE_OP")
                    if name in ['connect', 'execute', 'cursor']: features.append("DB_OP")

        # Normalizar para texto que a LSTM entende
        structure_signature = " ".join(features)
        
        return {
            "name": func_name,
            "doc": docstring,
            "signature": structure_signature,
            "raw_tokens": list(set(features)) # Bag of Structural Words
        }