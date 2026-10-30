from django.contrib import admin

from .models import Alarme, Leitura, Local, Rack


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ['nome', 'usuario']


@admin.register(Rack)
class RackAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'local', 'setor', 'temp_min', 'temp_max', 'umid_min', 'umid_max', 'energia_max']
    list_filter = ['local', 'setor']


@admin.register(Leitura)
class LeituraAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'rack', 'temperatura', 'umidade', 'energia_kw', 'porta_aberta', 'fumaca']
    list_filter = ['rack__local', 'porta_aberta', 'fumaca']
    date_hierarchy = 'timestamp'


@admin.register(Alarme)
class AlarmeAdmin(admin.ModelAdmin):
    list_display = ['inicio', 'fim', 'rack', 'tipo', 'severidade', 'valor', 'reconhecido']
    list_filter = ['tipo', 'severidade', 'reconhecido', 'rack__local']
    date_hierarchy = 'inicio'
