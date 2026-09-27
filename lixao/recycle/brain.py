"""
DOXOADE BRAIN v14.0 (Batching Maestro).
Orquestra o treino em bathes reais para máxima performance.
"""
import click
import os
import time
import numpy as np
from colorama import Fore, Style
from doxoade.neural.core import Tokenizer, CamadaEmbedding, LSTM, softmax, save_json, load_json
from doxoade.neural.adapter import BrainLoader
from doxoade.neural.logic import ArquitetoLogico
from doxoade.neural.profiler import NeuralProfiler

BRAIN_PATH = os.path.expanduser("~/.doxoade/cortex.json")

@click.group()
def brain():
    """🧠 Motor Neural (Batching Maestro)."""
    pass

@brain.command()
@click.option('--epochs', default=200, help='Ciclos totais.')
@click.option('--batch', default=128, help='Tamanho do Batch Real.')
@click.option('--samples', default=500, help='Quantidade de dados sintéticos.')
@click.option('--prune', is_flag=True, help='Ativa a poda neural.')
@click.option('--profile', is_flag=True, help='Ativa análise de gargalos.')
def train(epochs, batch, samples, prune, profile):
    
    with NeuralProfiler(enabled=profile):
        loader = BrainLoader()
        tok = Tokenizer()
        
        if os.path.exists(BRAIN_PATH):
            try:
                state = load_json(BRAIN_PATH)
                if 'tokenizer' in state: tok = Tokenizer.from_dict(state['tokenizer'])
            except Exception as e:
                import sys, os
                _, exc_obj, exc_tb = sys.exc_info()
                f_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                line_n = exc_tb.tb_lineno
                print(f"\033[1;34m[ FORENSIC ]\033[0m \033[1mFile: {f_name} | L: {line_n} | Func: train\033[0m")
                print(f"\033[31m  ■ Type: {type(e).__name__} | Value: {e}\033[0m")
        
        print(Fore.YELLOW + "--- Preparando Vocabulário Global ---" + Style.RESET_ALL)
        sample_level_3 = loader.get_training_data(limit=100, difficulty=3)
        all_text = [p[0] + " " + p[1] for p in sample_level_3]
        tok.treinar(all_text)
        
        EMBED_DIM = 32
        HIDDEN_SIZE = 128
        embed = CamadaEmbedding(tok.contador, EMBED_DIM)
        lstm = LSTM(EMBED_DIM, HIDDEN_SIZE, tok.contador)
        
        if os.path.exists(BRAIN_PATH):
             try:
                state = load_json(BRAIN_PATH)
                embed.load_state_dict(state['embed'])
                lstm.load_state_dict(state['lstm'])
                print(Fore.GREEN + "   💉 Córtex carregado." + Style.RESET_ALL)
             except Exception as e: 
                print(Fore.RED + f"   [Erro ao carregar JSON: {e} - Reiniciando]" + Style.RESET_ALL)
        
# [DOX-UNUSED]         stats = {"skipped": 0, "trained": 0, "surprise_threshold": 0.5}

        def prepare_batch(sequences, pad_token_id=0):
            """Transforma lista de sequências em matriz Batch X Seq."""
            max_len = max(len(s) for s in sequences)
            # Full para padronizar
            batch_matrix = np.full((len(sequences), max_len), pad_token_id, dtype=np.int32)
            for i, seq in enumerate(sequences):
                batch_matrix[i, :len(seq)] = seq
            return batch_matrix

        def train_epoch_batched(raw_dataset, lr, batch_size):
            total_loss = 0
            # IDs de todas as sequências (Seq, Batch)
            all_ids = []
            for inp, tgt in raw_dataset:
                full_seq = inp + " " + tgt + " ENDMARKER"
                all_ids.append(tok.converter_para_ids(full_seq))

            np.random.shuffle(all_ids) # Embaralha
            
            # Divide em lotes
            for i in range(0, len(all_ids), batch_size):
                batch_sequences = all_ids[i : i + batch_size]
                if not batch_sequences: break
                
                # Prepara os inputs e targets para o batch
                X_batch_list = [s[:-1] for s in batch_sequences]
                Y_batch_list = [s[1:] for s in batch_sequences]
                
                # Padding para criar tensores retangulares
                X_batch_padded = prepare_batch(X_batch_list, tok.vocabulario.get("<PAD>", 0))
                Y_batch_padded = prepare_batch(Y_batch_list, tok.vocabulario.get("<PAD>", 0))
                
                # --- FORWARD PASS EM BATCH ---
                # X_batch_padded: (Batch, Seq) -> Transpose para (Seq, Batch)
                X_batch_T = X_batch_padded.T # (MaxSeqLen, Batch)
                
                # Embed: (MaxSeqLen, Batch, EmbedDim)
                vetores = embed.forward(X_batch_T)
                
                # LSTM: (MaxSeqLen, Batch, Vocab)
                logits, _, _ = lstm.forward(vetores) 
                
                # Loss (Calculada em todos os tokens do batch, mascarando o padding)
                flat_logits = logits.reshape(-1, tok.contador) # (TotalTokensNoBatch, Vocab)
                flat_targets = Y_batch_padded.T.flatten() # (TotalTokensNoBatch,)
                
                # Máscara para ignorar tokens de padding na loss
                pad_mask = (flat_targets != tok.vocabulario.get("<PAD>", 0)).astype(np.float32)
                
                probs = softmax(flat_logits)
                probs = np.clip(probs, 1e-7, 1.0 - 1e-7)
                
                rows = np.arange(len(flat_targets))
                correct_probs = probs[rows, flat_targets]
                
                loss_per_token = -np.log(correct_probs) * pad_mask
                loss = np.sum(loss_per_token) / (np.sum(pad_mask) + 1e-8)
                total_loss += loss
                
                # --- BACKWARD PASS EM BATCH ---
                dY_flat = probs.copy()
                dY_flat[rows, flat_targets] -= 1
                dY_flat *= pad_mask[:, np.newaxis] # Zera gradiente do PAD
                dY_flat /= (np.sum(pad_mask) + 1e-8) # Normaliza pelo tamanho válido
                
                dY_3d = dY_flat.reshape(logits.shape) # (MaxSeqLen, Batch, Vocab)
                
                dInputs = lstm.accumulate_grad(dY_3d) # (MaxSeqLen, Batch, Embed)
                embed.accumulate_grad(dInputs.reshape(-1, EMBED_DIM))
                
                # Update
                lstm.apply_update(lr, batch_size=len(batch_sequences)) # Update com batch_size real
                embed.apply_update(lr, batch_size=len(batch_sequences))
                
            return total_loss / (len(all_ids) / batch_size) # Retorna perda média por batch

        lr = 0.01
        start_time = time.time()
        
        # --- CURRICULUM LOOP ---
        phase1_end = int(epochs * 0.2) 
        phase2_end = int(epochs * 0.6) 
        phase3_end = int(epochs * 0.9) 
        
        current_difficulty = 0
        
        for e in range(epochs):
            new_difficulty = 1
            if e > phase1_end: new_difficulty = 2
            if e > phase2_end: new_difficulty = 3
            if e > phase3_end: new_difficulty = 4
            
            # Regenera dados ao mudar de fase
            if new_difficulty != current_difficulty:
                current_difficulty = new_difficulty
                print(Fore.MAGENTA + f"\n📚 --- INICIANDO FASE {current_difficulty} ---" + Style.RESET_ALL)
                
            raw_data = loader.get_training_data(limit=samples, difficulty=current_difficulty)
            
            epoch_loss = train_epoch_batched(raw_data, lr, batch)
            
            if e % 10 == 0:
                elapsed = time.time() - start_time
                msg = f"   Epoca {e} (Fase {current_difficulty}): Perda {epoch_loss:.4f} ({elapsed:.1f}s)"
                if prune and e > 20:
                     msg += f" | ✂️ {lstm.prune(5):.1f}%"
                print(msg)
                start_time = time.time()

        # Save Final
        state = {
            "embed": embed.get_state_dict(),
            "lstm": lstm.get_state_dict(),
            "tokenizer": tok.to_dict(),
            "surprise_threshold": 0.05 # Final fixo
        }
        
        save_json(state, BRAIN_PATH)
        click.echo(Fore.GREEN + "💾 Córtex treinado salvo." + Style.RESET_ALL)

@brain.command()
@click.argument('prompt')
@click.option('--temp', default=0.7)
def consult(prompt, temp):
    if not os.path.exists(BRAIN_PATH):
        click.echo("❌ Cérebro não encontrado.")
        return
        
    state = load_json(BRAIN_PATH)
    
    tok = Tokenizer.from_dict(state['tokenizer'])
    vocab_size = tok.contador
    
    embed_dim = len(state['embed']['E'][0][0]) 
    hidden_size = len(state['lstm']['Wf'][0][0])
    
    embed = CamadaEmbedding(vocab_size, embed_dim)
    lstm = LSTM(embed_dim, hidden_size, vocab_size)
    
    embed.load_state_dict(state['embed'])
    lstm.load_state_dict(state['lstm'])
    
    arquiteto = ArquitetoLogico()
    
    try: input_ids = tok.converter_para_ids(prompt)
    except Exception: return

    curr = input_ids[0]
    h, c = None, None
    texto = [tok.inverso.get(str(curr))]
    
    # Pre-fill
    for next_id in input_ids[1:]:
        palavra = tok.inverso.get(str(next_id))
        arquiteto.observar(palavra)
        x = embed.forward(np.array([curr]))
        # Forward agora espera (Seq, Batch, Input) ou (Seq, Input)
        x_in = x.reshape(1, -1) # (1, Input_Dim)
        _, h, c = lstm.forward(x_in, h_prev=h, c_prev=c)
        curr = next_id
        texto.append(palavra)
        
    click.echo(Fore.CYAN + f"Prompt: {' '.join(texto)} " + Fore.GREEN, nl=False)
    
    for _ in range(30):
        x = embed.forward(np.array([curr]))
        x_in = x.reshape(1, -1) # (1, Input_Dim)
        out, h, c = lstm.forward(x_in, h_prev=h, c_prev=c)
        
        logits = out.flatten() # out é (1, 1, Vocab)
        logits = logits / temp
        probs = softmax(logits.reshape(1, -1)).flatten()
        
        top_indices = np.argsort(probs)[::-1][:10]
        soma = np.sum(probs[top_indices])
        if soma > 0: top_probs = probs[top_indices] / soma
        else: top_probs = np.ones(len(top_indices)) / len(top_indices)
        
        escolha = None
        for _ in range(10): 
            try:
                idx = np.random.choice(top_indices, p=top_probs)
            except Exception: idx = top_indices[0]
            
            cand = tok.inverso.get(str(idx), "?") # Chave str
            aprovado, _ = arquiteto.validar(cand)
            if aprovado:
                escolha = int(idx)
                break
        
        if escolha is None:
            sug = arquiteto.sugerir_correcao()
            if sug: escolha = tok.vocabulario.get(sug)
            else: escolha = int(top_indices[0])

        if escolha is None: break 
        
        palavra = tok.inverso.get(str(escolha))
        if palavra == "ENDMARKER":
            click.echo(Fore.YELLOW + " [FIM]" + Style.RESET_ALL)
            break
            
        click.echo(f"{palavra} ", nl=False)
        
        h, c = h, c
        curr = escolha
        arquiteto.observar(palavra)

if __name__ == "__main__":
    pass