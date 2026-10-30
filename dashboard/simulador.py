"""
Gerador de dados fictícios para a demonstração.

A Vercel não mantém processos rodando em segundo plano, então em vez de um "robô"
injetando leituras, o simulador alcança o tempo atual sempre que alguém abre o painel:
ele cria as leituras que faltam desde a última, em intervalos fixos de INTERVALO.
As leituras são determinísticas por (rack, horário), então simular duas vezes o
mesmo período gera exatamente os mesmos dados.
"""
import math
import random
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import Alarme, EstadoSimulacao, Leitura, Rack

INTERVALO = timedelta(minutes=5)
# Se o site ficar muito tempo sem acesso, preenche só as últimas horas para a requisição não demorar
MAX_ATRASO = timedelta(hours=12)
# Evita rodar o simulador a cada atualização automática do painel
ESPERA_MINIMA = timedelta(seconds=20)


@dataclass
class _Estado:
    temperatura: float
    umidade: float
    energia_kw: float
    porta_aberta: bool = False
    fumaca: bool = False


def alinhar(momento):
    """Arredonda para baixo no múltiplo de INTERVALO (ex.: 10:37 -> 10:35)."""
    segundos = int(INTERVALO.total_seconds())
    return momento - timedelta(seconds=int(momento.timestamp()) % segundos, microseconds=momento.microsecond)


def _perfil(rack):
    """Valores típicos de cada rack, variando um pouco entre eles."""
    return _Estado(
        temperatura=21.5 + (rack.pk % 5) * 0.6,
        umidade=47 + (rack.pk % 3) * 2,
        energia_kw=2.2 + (rack.pk % 4) * 0.5,
    )


def _proxima(rack, anterior, momento):
    rng = random.Random(f"{rack.pk}-{int(momento.timestamp())}")
    base = _perfil(rack)
    # Ciclo diário: mais quente e com mais carga à tarde
    hora = timezone.localtime(momento).hour + timezone.localtime(momento).minute / 60
    ciclo = math.sin(2 * math.pi * (hora - 9) / 24)

    temperatura = anterior.temperatura + 0.25 * (base.temperatura + 0.8 * ciclo - anterior.temperatura)
    temperatura += rng.gauss(0, 0.25)
    if rng.random() < 0.006:  # falha de refrigeração
        temperatura += rng.uniform(4, 8)
    elif rng.random() < 0.002:  # ar-condicionado exagerado
        temperatura -= rng.uniform(4, 6)

    umidade = anterior.umidade + 0.25 * (base.umidade - anterior.umidade) + rng.gauss(0, 0.6)
    if rng.random() < 0.004:
        umidade += rng.choice([-1, 1]) * rng.uniform(10, 16)

    energia = anterior.energia_kw + 0.3 * (base.energia_kw * (1 + 0.15 * ciclo) - anterior.energia_kw)
    energia += rng.gauss(0, 0.08)
    if rng.random() < 0.003:  # pico de processamento
        energia += rng.uniform(2, 3.5)

    porta = rng.random() < (0.55 if anterior.porta_aberta else 0.006)
    fumaca = rng.random() < (0.3 if anterior.fumaca else 0.0005)

    return _Estado(
        temperatura=round(temperatura, 1),
        umidade=round(min(max(umidade, 5), 95), 1),
        energia_kw=round(max(energia, 0.3), 2),
        porta_aberta=porta,
        fumaca=fumaca,
    )


def avaliar(rack, leitura):
    """Retorna {tipo: (severidade, valor)} com as condições de alarme da leitura."""
    S = Alarme.Severidade
    T = Alarme.Tipo
    violacoes = {}
    t, u, e = leitura.temperatura, leitura.umidade, leitura.energia_kw
    if t > rack.temp_max:
        violacoes[T.TEMP_ALTA] = (S.CRITICO if t >= rack.temp_max + 3 else S.AVISO, t)
    elif t < rack.temp_min:
        violacoes[T.TEMP_BAIXA] = (S.CRITICO if t <= rack.temp_min - 3 else S.AVISO, t)
    if u > rack.umid_max:
        violacoes[T.UMID_ALTA] = (S.CRITICO if u >= rack.umid_max + 10 else S.AVISO, u)
    elif u < rack.umid_min:
        violacoes[T.UMID_BAIXA] = (S.CRITICO if u <= rack.umid_min - 10 else S.AVISO, u)
    if e > rack.energia_max:
        violacoes[T.ENERGIA_ALTA] = (S.CRITICO if e >= rack.energia_max * 1.2 else S.AVISO, e)
    if leitura.porta_aberta:
        violacoes[T.PORTA_ABERTA] = (S.AVISO, None)
    if leitura.fumaca:
        violacoes[T.FUMACA] = (S.CRITICO, None)
    return violacoes


def simular_rack(rack, anterior, momentos, abertos):
    """
    Gera as leituras de um rack nos momentos informados e atualiza os alarmes.
    `abertos` é {tipo: Alarme} com os alarmes ativos do rack (é alterado no lugar).
    Retorna (leituras, alarmes_novos, alarmes_alterados), ainda sem salvar.
    """
    estado = anterior or _perfil(rack)
    leituras, novos, alterados = [], [], {}
    for momento in momentos:
        estado = _proxima(rack, estado, momento)
        leitura = Leitura(rack=rack, timestamp=momento, **estado.__dict__)
        leituras.append(leitura)

        violacoes = avaliar(rack, leitura)
        for tipo, alarme in list(abertos.items()):
            if tipo not in violacoes:
                alarme.fim = momento
                del abertos[tipo]
                if alarme.pk:
                    alterados[alarme.pk] = alarme
        for tipo, (severidade, valor) in violacoes.items():
            alarme = abertos.get(tipo)
            if alarme is None:
                alarme = Alarme(rack=rack, tipo=tipo, severidade=severidade, valor=valor, inicio=momento)
                abertos[tipo] = alarme
                novos.append(alarme)
                continue
            # Alarme já aberto: guarda o pior valor e eleva a severidade se piorar
            if valor is not None and (alarme.valor is None or _pior(tipo, valor, alarme.valor)):
                alarme.valor = valor
                if severidade == Alarme.Severidade.CRITICO:
                    alarme.severidade = severidade
                if alarme.pk:
                    alterados[alarme.pk] = alarme
    return leituras, novos, list(alterados.values())


def _pior(tipo, novo, atual):
    if tipo in (Alarme.Tipo.TEMP_BAIXA, Alarme.Tipo.UMID_BAIXA):
        return novo < atual
    return novo > atual


def salvar(leituras, novos, alterados):
    Leitura.objects.bulk_create(leituras, batch_size=1000, ignore_conflicts=True)
    Alarme.objects.bulk_create(novos, batch_size=500)
    if alterados:
        Alarme.objects.bulk_update(alterados, ['fim', 'valor', 'severidade'])


def simular_ate_agora(agora=None):
    """Cria as leituras que faltam até agora para todos os racks. Retorna quantas criou."""
    agora = agora or timezone.now()
    alvo = alinhar(agora)
    EstadoSimulacao.objects.get_or_create(pk=1)

    with transaction.atomic():
        # Se outra requisição já está simulando, não faz nada
        estado = EstadoSimulacao.objects.select_for_update(skip_locked=True).filter(pk=1).first()
        if estado is None:
            return 0
        if estado.ultima_execucao and agora - estado.ultima_execucao < ESPERA_MINIMA:
            return 0

        total = 0
        racks = Rack.objects.annotate(ultima=Max('leituras__timestamp')).filter(
            Q(ultima__lt=alvo) | Q(ultima__isnull=True)
        )
        for rack in racks:
            anterior = rack.leituras.first()
            inicio = alvo - MAX_ATRASO
            if rack.ultima:
                inicio = max(rack.ultima + INTERVALO, inicio)
            momentos = []
            while inicio <= alvo:
                momentos.append(inicio)
                inicio += INTERVALO
            abertos = {a.tipo: a for a in rack.alarmes.filter(fim__isnull=True)}
            leituras, novos, alterados = simular_rack(rack, anterior, momentos, abertos)
            salvar(leituras, novos, alterados)
            total += len(leituras)

        estado.ultima_execucao = agora
        estado.save(update_fields=['ultima_execucao'])
        return total
