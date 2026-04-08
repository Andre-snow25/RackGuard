import csv
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import SensorData
import json

@csrf_exempt
def receber_dados_sensor(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            SensorData.objects.create(
                temperatura=data['temperatura'],
                umidade=data['umidade']
            )
            return JsonResponse({'status': 'sucesso'}, status=201)
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'status': 'erro', 'mensagem': 'Dados invalidos'}, status=400)
    return JsonResponse({'status': 'erro', 'mensagem': 'Metodo nao permitido'}, status=405)

def dashboard_view(request):
    leituras_tabela = SensorData.objects.all().order_by('-timestamp')[:20]
    leituras_grafico = list(reversed(leituras_tabela))
    context = {'leituras': leituras_tabela, 'grafico': leituras_grafico}
    if request.headers.get('HX-Request'):
        return render(request, 'dashboard/dados_parciais.html', context)
    return render(request, 'dashboard/index.html', context)

def exportar_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leituras_sensor.csv"'
    writer = csv.writer(response)
    writer.writerow(['Data/Hora', 'Temperatura', 'Umidade'])
    leituras = SensorData.objects.all().order_by('-timestamp')
    for leitura in leituras:
        writer.writerow([
            leitura.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
            leitura.temperatura,
            leitura.umidade
        ])
    return response