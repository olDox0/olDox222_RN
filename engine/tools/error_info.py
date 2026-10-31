# engine\tools\error_info.py
"""
EXEMPLOS

from engine.tools.error_info import handle_error
handle_error(e, context="NomeDaFuncaoOndeEstaOErro", debug=True)

except Exception as e:
    from .error_info import handle_error
    handle_error(e, context="Clone Detection JSON Parse", debug=True)

from engine.tools.error_info import formated_traceback
formated_traceback(e, "Encoding Reconfiguration")
"""

def handle_error(err: Exception, context: str='', silent: bool=False, debug: bool=False):
    """
    Manipulador padrão de erros do Doxoade.

    :param err: exceção capturada
    :param context: contexto da operação (ex: "carregando settings.json")
    :param silent: não exibe nada
    :param debug: exibe traceback completo
    """
    if silent:
        return
    err_type = type(err).__name__
    msg = str(err)
    prefix = '⚠️ [DOXOADE ERROR]'
    if context:
        print(f'{prefix} ({context}) -> {err_type}: {msg}')
    else:
        print(f'{prefix} {err_type}: {msg}')
    from traceback import print_exc
    if debug:
        print('---- TRACEBACK ----')
        print_exc()

def _extract_function_signatures(content: str) -> dict:
    """Extrai o mapa semântico de funções e seus argumentos (MPoT-7)."""
    if not content:
        return {}
    import ast
    try:
        tree = ast.parse(content)
        functions = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                functions[node.name] = {'args': args, 'is_async': isinstance(node, ast.AsyncFunctionDef)}
        return functions
    except SyntaxError:
        return {}
    except Exception as e:
        from .error_info import handle_error
        handle_error(e, context='analysis._extract_function_signatures', silent=True)
        return {}
        
def validate_command_bridge(ctx):
    """
    Verifica se um comando está tentando invocar outro e se o 
    fluxo de I/O está desobstruído.
    """
    if ctx.parent and ctx.parent.command.name == 'flow':
        # Se viemos do flow, o stdout deve ser direto, sem buffers agressivos
        import os
        os.environ['PYTHONUNBUFFERED'] = '1'
        
def print_forensic_exception():
    """O 'exc_tb' definitivo: Extrai a verdade do sistema."""
    import sys
    import os
    from traceback import print_tb
    
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if not exc_tb:
        return
        
    # Pega o frame mais profundo (onde o erro realmente ocorreu)
    curr_tb = exc_tb
    while curr_tb.tb_next:
        curr_tb = curr_tb.tb_next
        
    fname = os.path.split(curr_tb.tb_frame.f_code.co_filename)[1]
    line_n = curr_tb.tb_lineno
    
    print("\n\x1b[41;1m 🔥 CRASH FORENSE \x1b[0m")
    print(f"\x1b[31m ■ Local : {fname}:{line_n}")
    print(f" ■ Tipo  : {exc_type.__name__}")
    print(f" ■ Valor : {str(exc_obj)}\x1b[0m")
    print("\x1b[90m--- CADEIA DE EVENTOS ---")
    print_tb(exc_tb)
    print("-------------------------\x1b[0m")
    
def formated_traceback(e, title="Error"):
    import sys as _sys, os as _os
    from traceback import print_tb as _print_tb
    
    _, exc_obj, exc_tb = _sys.exc_info()
    fname = _os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    line_no = exc_tb.tb_lineno
    exc_val = str(exc_obj).replace("'", "")
    
    print(f"\033[31m ■ {title}")
    print(f" ■ Archive: {fname} - line: {line_no}")
    print(f" ■ Exception type: {type(e).__name__}")
    print(f" ■ Exception value: {exc_val}\033[0m")
    _print_tb(exc_tb)
    
