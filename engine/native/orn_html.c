// engine/native/orn_html.c
#include <stdint.h>
#include <stddef.h>
#include <ctype.h>
#include <string.h>

#if defined(_WIN32)
#define ORN_API __declspec(dllexport)
#else
#define ORN_API
#endif

// Função auxiliar para comparar prefixos ignorando case
static int case_insensitive_match(const char *str, const char *prefix, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (tolower((unsigned char)str[i]) != tolower((unsigned char)prefix[i])) {
            return 0;
        }
    }
    return 1;
}

ORN_API size_t orn_strip_html(const char *input, size_t in_len, char *output) {
    size_t out_pos = 0;
    size_t i = 0;
    int in_tag = 0;
    int last_was_space = 1; // Começa como 1 para dar trim no início

    while (i < in_len) {
        if (input[i] == '<') {
            // Ignorar <!-- Comentários -->
            if (i + 3 < in_len && input[i+1] == '!' && input[i+2] == '-' && input[i+3] == '-') {
                i += 4;
                while (i + 2 < in_len && !(input[i] == '-' && input[i+1] == '-' && input[i+2] == '>')) {
                    i++;
                }
                i += 3;
                continue;
            }
            
            // Ignorar <script> e seu conteúdo
            if (i + 6 < in_len && case_insensitive_match(&input[i+1], "script", 6)) {
                i += 7;
                while (i + 8 < in_len) {
                    if (input[i] == '<' && input[i+1] == '/' && case_insensitive_match(&input[i+2], "script", 6) && input[i+8] == '>') {
                        i += 9;
                        break;
                    }
                    i++;
                }
                continue;
            }

            // Ignorar <style> e seu conteúdo
            if (i + 5 < in_len && case_insensitive_match(&input[i+1], "style", 5)) {
                i += 6;
                while (i + 7 < in_len) {
                    if (input[i] == '<' && input[i+1] == '/' && case_insensitive_match(&input[i+2], "style", 5) && input[i+7] == '>') {
                        i += 8;
                        break;
                    }
                    i++;
                }
                continue;
            }

            // Ignorar tags padrão <...>
            in_tag = 1;
            i++;
            continue;
        }

        if (in_tag) {
            if (input[i] == '>') {
                in_tag = 0;
                // Adiciona espaço após tag de bloco para evitar colagem de palavras (ex: </h1><p>)
                if (!last_was_space) {
                    output[out_pos++] = ' ';
                    last_was_space = 1;
                }
            }
            i++;
            continue;
        }

        // Processar texto (fora de tags)
        char c = input[i];
        if (isspace((unsigned char)c)) {
            if (!last_was_space) {
                // Preserva newlines como formatação básica
                if (c == '\n') {
                    output[out_pos++] = '\n';
                } else {
                    output[out_pos++] = ' ';
                }
                last_was_space = 1;
            }
        } else {
            output[out_pos++] = c;
            last_was_space = 0;
        }
        i++;
    }

    // Remover espaço final se houver
    if (out_pos > 0 && isspace((unsigned char)output[out_pos - 1])) {
        out_pos--;
    }

    output[out_pos] = '\0';
    return out_pos;
}