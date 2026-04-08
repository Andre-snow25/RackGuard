from django.urls import path
from .views import receber_dados_sensor, dashboard_view, exportar_csv

urlpatterns = [
    path('', dashboard_view, name='index'),
    path('api/sensor/', receber_dados_sensor, name='receber_dados_sensor'),
    path('exportar-csv/', exportar_csv, name='exportar_csv'),
]