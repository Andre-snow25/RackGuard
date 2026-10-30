from django.conf import settings
from django.db import models
from django.utils import timezone


class Local(models.Model):
    """Site/datacenter onde os racks ficam instalados."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='locais')
    nome = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)

    class Meta:
        ordering = ['nome']
        verbose_name_plural = 'locais'

    def __str__(self):
        return f"{self.nome} ({self.cidade})"


class Rack(models.Model):
    local = models.ForeignKey(Local, on_delete=models.CASCADE, related_name='racks')
    codigo = models.CharField(max_length=20, unique=True)
    descricao = models.CharField(max_length=100, blank=True)

    # Limites de alerta
    temp_min = models.FloatField('temperatura mínima (°C)', default=18)
    temp_max = models.FloatField('temperatura máxima (°C)', default=27)
    umid_min = models.FloatField('umidade mínima (%)', default=40)
    umid_max = models.FloatField('umidade máxima (%)', default=60)
    energia_max = models.FloatField('consumo máximo (kW)', default=5)

    class Meta:
        ordering = ['local__nome', 'codigo']

    def __str__(self):
        return self.codigo


class Leitura(models.Model):
    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name='leituras')
    timestamp = models.DateTimeField(default=timezone.now)
    temperatura = models.FloatField()
    umidade = models.FloatField()
    energia_kw = models.FloatField()
    porta_aberta = models.BooleanField(default=False)
    fumaca = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']
        constraints = [
            # Evita leituras duplicadas quando duas requisições simulam ao mesmo tempo
            models.UniqueConstraint(fields=['rack', 'timestamp'], name='leitura_unica_por_rack'),
        ]
        indexes = [models.Index(fields=['rack', '-timestamp'])]

    def __str__(self):
        return f"{self.rack} {self.timestamp:%d/%m %H:%M} - {self.temperatura}°C"


class Alarme(models.Model):
    class Tipo(models.TextChoices):
        TEMP_ALTA = 'temp_alta', 'Temperatura alta'
        TEMP_BAIXA = 'temp_baixa', 'Temperatura baixa'
        UMID_ALTA = 'umid_alta', 'Umidade alta'
        UMID_BAIXA = 'umid_baixa', 'Umidade baixa'
        ENERGIA_ALTA = 'energia_alta', 'Consumo de energia alto'
        PORTA_ABERTA = 'porta_aberta', 'Porta aberta'
        FUMACA = 'fumaca', 'Fumaça detectada'

    class Severidade(models.TextChoices):
        AVISO = 'aviso', 'Aviso'
        CRITICO = 'critico', 'Crítico'

    rack = models.ForeignKey(Rack, on_delete=models.CASCADE, related_name='alarmes')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    severidade = models.CharField(max_length=10, choices=Severidade.choices)
    valor = models.FloatField(null=True, blank=True)
    inicio = models.DateTimeField()
    fim = models.DateTimeField(null=True, blank=True)
    reconhecido = models.BooleanField(default=False)

    class Meta:
        ordering = ['-inicio']
        indexes = [models.Index(fields=['rack', 'fim'])]

    def __str__(self):
        return f"{self.rack} - {self.get_tipo_display()}"

    @property
    def ativo(self):
        return self.fim is None

    @property
    def duracao(self):
        return (self.fim or timezone.now()) - self.inicio


class EstadoSimulacao(models.Model):
    """Linha única usada como trava para que só uma requisição rode o simulador por vez."""
    ultima_execucao = models.DateTimeField(null=True, blank=True)
