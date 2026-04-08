from django.db import models

class SensorData(models.Model):
    temperatura = models.FloatField()
    umidade = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.timestamp} - T: {self.temperatura}°C | U: {self.umidade}%"