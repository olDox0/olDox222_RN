def calcular_risco_teste():
    try:
# [DOX-UNUSED]         x = 1 / 0  # Forçar erro
    except Exception as e:
        import sys, os
        _, exc_obj, exc_tb = sys.exc_info()
        f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        line_n = exc_tb.tb_lineno
        print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: calcular_risco_teste\033[0m")
        print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
        return False

if __name__ == "__main__":
    calcular_risco_teste()
