# native/nexus_logic.s
# Otimização Nexus para N2808 (x86_64)
# Operação: Fast Varint Masking (Branchless)

.section .text
.global fast_mask_varint

fast_nexus_mask:
    # %rdi = entrada (n)
    movq %rdi, %rax
    andq $0x7F, %rax    # Isola os 7 bits baixos
    orq  $0x80, %rax    # Seta o bit de continuação sem usar 'if'
    ret