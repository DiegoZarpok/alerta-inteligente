"""Limiares de cheia a partir do estudo da UESC.

Fonte: Farias, E. S.; Gomes, R. L. (2023). Revista Brasileira de Geografia Física, v. 16, n. 2,
p. 847-872. Tabela 14: vazões máximas por tempo de retorno (TR), ajustadas pela distribuição de
Gumbel às máximas anuais da estação Contorno da BR-101 (53180000).

No estudo, 2.430,19 m³/s (TR de 54 anos, a cheia de 1967) é a vazão a partir da qual o rio
extravasa e atinge o centro comercial de Itabuna. O estudo também registra que cheias com TR
acima de 3 anos já atingem comunidades ribeirinhas como a do Bananeira.
"""
import math

# Tabela 14 do estudo, estação Contorno da BR-101: TR (anos) -> (vazão m³/s, cota cm)
TABELA_UESC_CONTORNO = {
    2: (670.22, 481.23),
    5: (1219.50, 648.69),
    10: (1583.17, 759.56),
    20: (1932.01, 865.92),
    50: (2383.55, 1003.58),
    54: (2430.19, 1015.06),
    100: (2721.92, 1106.74),
}
TABELA_UESC_FERRADAS = {
    2: (508.74, 483.93), 5: (817.89, 659.19), 10: (1022.56, 775.22), 20: (1218.90, 886.53),
    50: (1473.03, 1030.60), 54: (1639.84, 1042.62), 100: (1663.47, 1138.56),
}


def variavel_reduzida(tr):
    """y = -ln(-ln(1 - 1/TR)) da distribuição de Gumbel."""
    return -math.log(-math.log(1 - 1 / tr))


def ajustar_gumbel(tabela=TABELA_UESC_CONTORNO):
    """Recupera os parâmetros u (posição) e alfa (escala) por mínimos quadrados: Q = u + alfa*y."""
    pontos = [(variavel_reduzida(tr), q) for tr, (q, _) in tabela.items()]
    n = len(pontos)
    my = sum(y for y, _ in pontos) / n
    mq = sum(q for _, q in pontos) / n
    alfa = sum((y - my) * (q - mq) for y, q in pontos) / sum((y - my) ** 2 for y, _ in pontos)
    return mq - alfa * my, alfa


U, ALFA = ajustar_gumbel()


def vazao_para_tr(tr):
    return U + ALFA * variavel_reduzida(tr)


def tr_da_vazao(q):
    """Tempo de retorno (anos) associado a uma vazão, pela mesma curva de Gumbel."""
    prob_nao_exceder = math.exp(-math.exp(-(q - U) / ALFA))
    return math.inf if prob_nao_exceder >= 1 else 1 / (1 - prob_nao_exceder)


def limiares():
    return {
        "tr2": vazao_para_tr(2),
        "tr3": vazao_para_tr(3),
        "tr54": TABELA_UESC_CONTORNO[54][0],
    }


def resumo():
    linhas = [f"Gumbel ajustado à Tabela 14 do estudo (Contorno da BR-101): u = {U:.1f} m³/s, alfa = {ALFA:.1f} m³/s",
              "TR (anos) | estudo (m³/s) | curva ajustada (m³/s)"]
    for tr, (q, _) in TABELA_UESC_CONTORNO.items():
        linhas.append(f"{tr:>9} | {q:>13.1f} | {vazao_para_tr(tr):>12.1f}")
    linhas.append(f"Limiar do modelo (TR de 3 anos, áreas ribeirinhas): {vazao_para_tr(3):.0f} m³/s")
    linhas.append(f"Limiar de extravasamento no centro (TR de 54 anos): {TABELA_UESC_CONTORNO[54][0]:.0f} m³/s")
    return "\n".join(linhas)
