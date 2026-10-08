@echo off
echo ============================================================
echo  ORN METALCRAFT: Treinamento Otimizado (Alder Lake Profile)
echo ============================================================

:: 1. Ativar o ambiente virtual
call venv\Scripts\activate.bat

:: 2. Configurar OpenMP para o i5-1235U (10 cores físicos + 2 hyperthreads = 12 threads lógicas)
:: Usaremos 10 threads para evitar overhead de scheduling nos E-cores
set OMP_NUM_THREADS=10
set OMP_PROC_BIND=spread
set OMP_PLACES=cores

:: 3. Variáveis do GGML para forçar o uso das instruções compiladas
set GGML_CPU_HBM=0
set GGML_CPU_ALL_VARIANTS=1

:: 4. Executar o binário compilado
echo [INFO] Iniciando treinamento com perfil Alder Lake...
native\llama-finetune.exe ^
  --model models/smol_sys/SmolLM2-135M-Instruct-F16.gguf ^
  --file data/training/brunnr_native_train.txt ^
  --output data/training/brunnr_c_finetuned.gguf ^
  -t 10 ^
  -c 512 ^
  -b 16 ^
  --epochs 1 ^
  -lr 5e-5

pause
