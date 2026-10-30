import csv
from datetime import datetime, timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Alarme, Leitura, Local, Rack
from .simulador import simular_ate_agora

PERIODOS = {'6h': timedelta(hours=6), '24h': timedelta(hours=24), '7d': timedelta(days=7)}


class LimitesForm(forms.ModelForm):
    class Meta:
        model = Rack
        fields = ['temp_min', 'temp_max', 'umid_min', 'umid_max', 'energia_max']

    def clean(self):
        dados = super().clean()
        for minimo, maximo in (('temp_min', 'temp_max'), ('umid_min', 'umid_max')):
            if dados.get(minimo) is not None and dados.get(maximo) is not None and dados[minimo] >= dados[maximo]:
                self.add_error(maximo, 'O máximo precisa ser maior que o mínimo.')
        return dados


def _data(valor, formato='%Y-%m-%dT%H:%M'):
    """Converte o valor de um <input> de data em datetime com fuso; None se vazio ou inválido."""
    try:
        return timezone.make_aware(datetime.strptime(valor, formato))
    except (TypeError, ValueError):
        return None


def _status(alarmes):
    severidades = {a.severidade for a in alarmes}
    if Alarme.Severidade.CRITICO in severidades:
        return 'critico'
    return 'aviso' if severidades else 'ok'


@login_required
def painel(request):
    simular_ate_agora()
    racks = list(
        Rack.objects.filter(local__usuario=request.user)
        .select_related('local')
        .annotate(ultima=Max('leituras__timestamp'))
    )
    filtro_ultimas = Q(pk__in=[])
    for rack in racks:
        if rack.ultima:
            filtro_ultimas |= Q(rack=rack, timestamp=rack.ultima)
    ultimas = {leitura.rack_id: leitura for leitura in Leitura.objects.filter(filtro_ultimas)}

    ativos = list(
        Alarme.objects.filter(rack__local__usuario=request.user, fim__isnull=True)
        .select_related('rack__local')
        .order_by('-severidade', '-inicio')  # 'critico' vem antes de 'aviso'
    )
    # {escola: {setor: [pontos]}}
    escolas = {}
    for rack in racks:
        rack.leitura = ultimas.get(rack.pk)
        rack.alarmes_ativos = [a for a in ativos if a.rack_id == rack.pk]
        rack.status = _status(rack.alarmes_ativos)
        escolas.setdefault(rack.local, {}).setdefault(rack.get_setor_display(), []).append(rack)
    for escola, setores in escolas.items():
        escola.status = _status([a for pontos in setores.values() for r in pontos for a in r.alarmes_ativos])

    leituras = [r.leitura for r in racks if r.leitura]
    context = {
        'escolas': escolas,
        'ativos': ativos,
        'resumo': {
            'escolas': len(escolas),
            'racks': len(racks),
            'criticos': sum(a.severidade == Alarme.Severidade.CRITICO for a in ativos),
            'avisos': sum(a.severidade == Alarme.Severidade.AVISO for a in ativos),
            'temp_media': sum(l.temperatura for l in leituras) / len(leituras) if leituras else None,
            'energia_total': sum(l.energia_kw for l in leituras),
            'portas_abertas': sum(l.porta_aberta for l in leituras),
        },
        'atualizado': timezone.now(),
    }
    return render(request, 'dashboard/painel.html', context)


@login_required
def rack_detalhe(request, codigo):
    rack = get_object_or_404(Rack.objects.select_related('local'), codigo=codigo, local__usuario=request.user)
    if request.method == 'POST':
        form = LimitesForm(request.POST, instance=rack)
        if form.is_valid():
            form.save()
            return redirect('rack_detalhe', codigo=rack.codigo)
    else:
        simular_ate_agora()
        form = LimitesForm(instance=rack)

    periodo = request.GET.get('periodo', '24h')
    if periodo not in PERIODOS:
        periodo = '24h'
    leituras = list(
        rack.leituras.filter(timestamp__gte=timezone.now() - PERIODOS[periodo]).order_by('timestamp')
    )
    resumo = rack.leituras.filter(timestamp__gte=timezone.now() - PERIODOS[periodo]).aggregate(
        temp_media=Avg('temperatura'), temp_max=Max('temperatura'), umid_media=Avg('umidade'),
    )
    alarmes = list(rack.alarmes.all()[:15])
    ativos = [a for a in alarmes if a.ativo]
    formato = '%d/%m %H:%M' if periodo == '7d' else '%H:%M'
    grafico = {
        'labels': [timezone.localtime(l.timestamp).strftime(formato) for l in leituras],
        'temperatura': [l.temperatura for l in leituras],
        'umidade': [l.umidade for l in leituras],
        'energia': [l.energia_kw for l in leituras],
        'limites': {
            'temperatura': [rack.temp_min, rack.temp_max],
            'umidade': [rack.umid_min, rack.umid_max],
            'energia': [None, rack.energia_max],
        },
    }
    context = {
        'rack': rack,
        'form': form,
        'grafico': grafico,
        'periodo': periodo,
        'periodos': PERIODOS.keys(),
        'leituras': leituras,
        'ultima': leituras[-1] if leituras else None,
        'recentes': leituras[:-13:-1],
        'resumo': resumo,
        'alarmes': alarmes,
        'status': _status(ativos),
    }
    return render(request, 'dashboard/rack.html', context)


@login_required
def alarmes(request):
    simular_ate_agora()
    qs = Alarme.objects.filter(rack__local__usuario=request.user).select_related('rack__local')
    f = request.GET
    if f.get('status') == 'ativos':
        qs = qs.filter(fim__isnull=True)
    elif f.get('status') == 'encerrados':
        qs = qs.filter(fim__isnull=False)
    if f.get('severidade'):
        qs = qs.filter(severidade=f['severidade'])
    if f.get('tipo'):
        qs = qs.filter(tipo=f['tipo'])
    if f.get('local'):
        qs = qs.filter(rack__local_id=f['local'])
    if f.get('setor'):
        qs = qs.filter(rack__setor=f['setor'])
    if inicio := _data(f.get('inicio'), '%Y-%m-%d'):
        qs = qs.filter(inicio__gte=inicio)
    if fim := _data(f.get('fim'), '%Y-%m-%d'):
        qs = qs.filter(inicio__lt=fim + timedelta(days=1))

    por_tipo = qs.values('tipo').annotate(total=Count('id')).order_by('-total')
    nomes = dict(Alarme.Tipo.choices)
    context = {
        'pagina': Paginator(qs, 50).get_page(f.get('page')),
        'total': qs.count(),
        'por_tipo': [(nomes[t['tipo']], t['total']) for t in por_tipo],
        'filtros': f,
        'tipos': Alarme.Tipo.choices,
        'severidades': Alarme.Severidade.choices,
        'locais': Local.objects.filter(usuario=request.user),
        'setores': Rack.Setor.choices,
        'querystring': _sem_pagina(f),
    }
    return render(request, 'dashboard/alarmes.html', context)


def _sem_pagina(querydict):
    params = querydict.copy()
    params.pop('page', None)
    return params.urlencode()


@login_required
@require_POST
def reconhecer_alarme(request, pk):
    alarme = get_object_or_404(Alarme, pk=pk, rack__local__usuario=request.user)
    alarme.reconhecido = True
    alarme.save(update_fields=['reconhecido'])
    return redirect(request.POST.get('next') or 'alarmes')


def _leituras_filtradas(request):
    qs = Leitura.objects.filter(rack__local__usuario=request.user).select_related('rack__local')
    f = request.GET
    if f.get('local'):
        qs = qs.filter(rack__local_id=f['local'])
    if f.get('setor'):
        qs = qs.filter(rack__setor=f['setor'])
    if f.get('rack'):
        qs = qs.filter(rack__codigo=f['rack'])
    inicio = _data(f.get('inicio')) or timezone.now() - timedelta(hours=24)
    qs = qs.filter(timestamp__gte=inicio)
    if fim := _data(f.get('fim')):
        qs = qs.filter(timestamp__lte=fim)
    return qs.order_by('-timestamp', 'rack__codigo')


@login_required
def historico(request):
    simular_ate_agora()
    qs = _leituras_filtradas(request)
    context = {
        'pagina': Paginator(qs, 100).get_page(request.GET.get('page')),
        'filtros': request.GET,
        'racks': Rack.objects.filter(local__usuario=request.user).select_related('local'),
        'locais': Local.objects.filter(usuario=request.user),
        'setores': Rack.Setor.choices,
        'querystring': _sem_pagina(request.GET),
    }
    return render(request, 'dashboard/historico.html', context)


@login_required
def exportar_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="leituras_rackguard.csv"'
    response.write('﻿')  # BOM para o Excel reconhecer os acentos
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Data/Hora', 'Escola', 'Setor', 'Código', 'Ponto', 'Temperatura (°C)', 'Umidade (%)',
                     'Energia (kW)', 'Porta', 'Fumaça'])
    for l in _leituras_filtradas(request).iterator():
        writer.writerow([
            timezone.localtime(l.timestamp).strftime('%d/%m/%Y %H:%M'), l.rack.local.nome,
            l.rack.get_setor_display(), l.rack.codigo, l.rack.descricao,
            str(l.temperatura).replace('.', ','), str(l.umidade).replace('.', ','),
            str(l.energia_kw).replace('.', ','), 'Aberta' if l.porta_aberta else 'Fechada',
            'Sim' if l.fumaca else 'Não',
        ])
    return response
