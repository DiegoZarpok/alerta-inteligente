"""Gera séries SINTÉTICAS só para os testes automáticos do código.

Nunca são usadas nos resultados do projeto: os resultados vêm dos dados reais da ANA.
As cheias anuais seguem a curva de Gumbel do estudo da UESC, para o teste ficar parecido com o real.
"""
import csv
import math
import random
from datetime import date, timedelta

from src.coleta.ana import ESTACOES
from src.modelo import limiares


def gerar(pasta, ano_inicio=1968, ano_fim=2019, semente=7):
    rnd = random.Random(semente)
    dias = (date(ano_fim, 12, 31) - date(ano_inicio, 1, 1)).days + 1
    datas = [date(ano_inicio, 1, 1) + timedelta(days=i) for i in range(dias)]
    chuva_bacia = [0.0] * dias

    def chuvoso(d):
        return d.month in (11, 12, 1, 2, 3, 4)

    for i, d in enumerate(datas):
        if rnd.random() < (0.35 if chuvoso(d) else 0.18):
            chuva_bacia[i] = rnd.expovariate(1 / (9 if chuvoso(d) else 4))

    # uma tempestade grande por ano, com pico de vazão sorteado pela curva de Gumbel da UESC
    picos = {}
    for ano in range(ano_inicio, ano_fim + 1):
        alvo = limiares.U - limiares.ALFA * math.log(-math.log(rnd.random()))
        inicio = date(ano, rnd.choice([11, 12, 1, 2, 3, 4]), rnd.randint(1, 25))
        if inicio.month in (11, 12):
            inicio = inicio.replace(year=ano - 1) if ano > ano_inicio else inicio
        idx = (inicio - datas[0]).days
        if 0 <= idx < dias - 5:
            picos[idx] = max(alvo, 50)
            for k in range(3):
                chuva_bacia[idx + k] += alvo / 22 * (0.6 + 0.4 * rnd.random())

    # reservatório linear: a vazão responde à chuva dos últimos dias
    vazao, armazenado = [0.0] * dias, 400.0
    for i in range(dias):
        armazenado = armazenado * 0.93 + chuva_bacia[i] * 55
        vazao[i] = 4 + armazenado * 0.07
    for idx, alvo in picos.items():
        janela = range(idx, min(idx + 6, dias))
        atual = max(vazao[j] for j in janela)
        fator = alvo / atual if atual > 0 else 1
        for j in janela:
            vazao[j] *= fator if fator > 1 else 1
    ferradas = [v * 0.66 for v in vazao[1:]] + [vazao[-1] * 0.66]

    pasta.mkdir(parents=True, exist_ok=True)
    for codigo, info in ESTACOES.items():
        with open(pasta / f"{codigo}_{info['tipo']}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["data", "valor", "nivel_consistencia"])
            for i, d in enumerate(datas):
                if info["tipo"] == "vazao":
                    v = vazao[i] if codigo == "53180000" else ferradas[i]
                else:
                    v = max(0.0, chuva_bacia[i] * (0.7 + 0.6 * rnd.random()))
                    if rnd.random() < 0.03:
                        v = ""  # falhas de leitura, como acontece nos postos reais
                w.writerow([d.isoformat(), "" if v == "" else round(v, 1), 2])
