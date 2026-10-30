from .models import Alarme


def alarmes_ativos(request):
    """Quantidade de alarmes ativos, mostrada no menu de todas as páginas."""
    if not request.user.is_authenticated:
        return {}
    ativos = Alarme.objects.filter(rack__local__usuario=request.user, fim__isnull=True)
    return {
        'menu_alarmes': ativos.count(),
        'menu_criticos': ativos.filter(severidade=Alarme.Severidade.CRITICO).count(),
    }
