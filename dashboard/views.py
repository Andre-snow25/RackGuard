import csv
import json
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta, datetime
from .models import SensorData

@csrf_exempt
def receber_dados_sensor(request):
    if request.method == 'POST':
        try:
            # ACEITA TANTO JSON QUANTO POST COMUM
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST

            SensorData.objects.create(
                temperatura=data['temperatura'],
                umidade=data['umidade']
            )
            return JsonResponse({'status': 'sucesso'}, status=201)
        except (KeyError, json.JSONDecodeError, TypeError):
            return JsonResponse({'status': 'erro', 'mensagem': 'Dados invalidos'}, status=400)
    return JsonResponse({'status': 'erro', 'mensagem': 'Metodo nao permitido'}, status=405)

def dashboard_view(request):
    agora = timezone.now()
    uma_hora_atras = agora - timedelta(hours=1)
    leituras_agora = SensorData.objects.filter(timestamp__gte=uma_hora_atras).order_by('-timestamp')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    leituras_historico = None
    if data_inicio and data_fim:
        try:
            start = datetime.strptime(data_inicio, '%Y-%m-%dT%H:%M')
            end = datetime.strptime(data_fim, '%Y-%m-%dT%H:%M')
            leituras_historico = SensorData.objects.filter(timestamp__range=(start, end)).order_by('-timestamp')
        except ValueError:
            pass
    leituras_grafico = list(reversed(leituras_agora[:20]))
    context = {
        'leituras': leituras_agora,
        'leituras_historico': leituras_historico,
        'grafico': leituras_grafico,
        'filtros': {'inicio': data_inicio, 'fim': data_fim}
    }
    if request.headers.get('HX-Request') and not data_inicio:
        return render(request, 'dashboard/dados_parciais.html', context)
    return render(request, 'dashboard/index.html', context)

def exportar_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leituras_sensor.csv"'
    writer = csv.writer(response)
    writer.writerow(['Data/Hora', 'Temperatura', 'Umidade'])
    leituras = SensorData.objects.all().order_by('-timestamp')
    for leitura in leituras:
        writer.writerow([leitura.timestamp.strftime('%d/%m/%Y %H:%M:%S'), leitura.temperatura, leitura.umidade])
    return response