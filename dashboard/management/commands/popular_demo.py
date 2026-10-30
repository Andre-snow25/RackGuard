import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import Local, Rack
from dashboard.simulador import INTERVALO, alinhar, salvar, simular_rack

# (nome, cidade, prefixo, quantidade de racks, limites diferentes do padrão)
LOCAIS = [
    ('Datacenter Central', 'São Paulo', 'SP', 4, {}),
    ('Filial Campinas', 'Campinas', 'CPS', 3, {'temp_max': 26}),
    ('Unidade Rio', 'Rio de Janeiro', 'RJ', 3, {'umid_max': 65}),
    ('Escritório Curitiba', 'Curitiba', 'CWB', 2, {'temp_min': 17, 'energia_max': 4.5}),
]


class Command(BaseCommand):
    help = 'Cria o usuário de demonstração, locais, racks e um histórico fictício de leituras e alarmes.'

    def add_arguments(self, parser):
        parser.add_argument('--email', default='rackguard@gmail.com')
        parser.add_argument('--senha', default=os.environ.get('DEMO_PASSWORD', 'rackguard123'))
        parser.add_argument('--dias', type=int, default=7, help='Dias de histórico a gerar')

    def handle(self, *args, email, senha, dias, **options):
        User = get_user_model()
        usuario, criado = User.objects.get_or_create(username=email, defaults={'email': email})
        usuario.set_password(senha)
        usuario.save()
        self.stdout.write(f"Usuário {email} {'criado' if criado else 'atualizado'}.")

        with transaction.atomic():
            # Recria do zero os dados fictícios desse usuário
            usuario.locais.all().delete()
            racks = []
            for nome, cidade, prefixo, quantidade, limites in LOCAIS:
                local = Local.objects.create(usuario=usuario, nome=nome, cidade=cidade)
                for i in range(1, quantidade + 1):
                    racks.append(Rack.objects.create(
                        local=local, codigo=f'{prefixo}-R{i:02d}', descricao=f'Rack {i} - {nome}', **limites,
                    ))

            fim = alinhar(timezone.now())
            momentos = []
            momento = fim - timedelta(days=dias)
            while momento <= fim:
                momentos.append(momento)
                momento += INTERVALO

            total_leituras = total_alarmes = 0
            for rack in racks:
                leituras, novos, _ = simular_rack(rack, None, momentos, {})
                salvar(leituras, novos, [])
                total_leituras += len(leituras)
                total_alarmes += len(novos)
                self.stdout.write(f'  {rack.codigo}: {len(leituras)} leituras, {len(novos)} alarmes')

        self.stdout.write(self.style.SUCCESS(
            f'Pronto: {len(racks)} racks, {total_leituras} leituras e {total_alarmes} alarmes em {dias} dias.'
        ))
