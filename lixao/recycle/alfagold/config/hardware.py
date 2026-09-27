# alfagold/config/hardware.py
import os
import multiprocessing

# Cache para não rodar detecção toda vez
_HW_CONFIG_CACHE = None

def get_hw_config():
    """
    Detecta capacidades do hardware sob demanda (Lazy).
    """
    global _HW_CONFIG_CACHE
    if _HW_CONFIG_CACHE is not None:
        return _HW_CONFIG_CACHE

    cpu_count = multiprocessing.cpu_count()
    
    # Heurística para Termux/Mobile
    is_mobile = "ANDROID_ROOT" in os.environ or cpu_count <= 4
    
    config = {}
    
    if is_mobile:
        # Apenas imprime se for a primeira vez que é chamado
        # print("📱 Modo Mobile (Termux) Detectado") 
        config['LUT_RESOLUTION'] = 32768
        config['BATCH_SIZE'] = 16
        config['D_MODEL'] = 64
        config['USE_THREADS'] = False
    else:
        # print("💻 Modo Desktop Detectado")
        config['LUT_RESOLUTION'] = 65536 # Reduzi para 65k por segurança numérica da LUT v2
        config['BATCH_SIZE'] = 64
        config['D_MODEL'] = 128
        config['USE_THREADS'] = True

    _HW_CONFIG_CACHE = config
    return config

# Proxies para acesso fácil (mas que chamam a função)
def get_resolution(): return get_hw_config()['LUT_RESOLUTION']