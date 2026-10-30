import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import Local, Rack
from dashboard.simulador import INTERVALO, alinhar, salvar, simular_rack

ESCOLAS = ['Escola 1', 'Escola 2', 'Escola 3']

S = Rack.Setor
# setor: (sigla do código, pontos monitorados, limites diferentes do padrão)
SETORES = {
    S.SERVIDOR: ('SRV', ['Servidor de Arquivos', 'Servidor Acadêmico'], {}),
    S.DATA_CENTER: ('DC', ['Rack Principal', 'Rack de Backup'], {'temp_max': 26, 'energia_max': 6}),
    S.RACKS: ('RCK', ['Rack Bloco A', 'Rack Bloco B', 'Rack Biblioteca'], {'energia_max': 4}),
    S.SALA_INFORMATICA: ('INF', ['Laboratório 1', 'Laboratório 2'],
                         {'temp_max': 30, 'umid_min': 35, 'umid_max': 70, 'energia_max': 3.5}),
    S.SALA_PROFESSORES: ('PROF', ['Sala dos Professores'],
                         {'temp_max': 30, 'umid_min': 35, 'umid_max': 70, 'energia_max': 1.5}),
}


class Command(BaseCommand):
    help = 'Cria o usuário de demonstração, as escolas, setores, pontos monitorados e um histórico fictício.'

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
            for n, nome in enumerate(ESCOLAS, start=1):
                escola = Local.objects.create(usuario=usuario, nome=nome)
                for setor, (sigla, pontos, limites) in SETORES.items():
                    for i, descricao in enumerate(pontos, start=1):
                        racks.append(Rack.objects.create(
                            local=escola, setor=setor, codigo=f'E{n}-{sigla}-{i:02d}', descricao=descricao, **limites,
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
                self.stdout.write(f'  {rack.codigo} ({rack.descricao}): {len(leituras)} leituras, {len(novos)} alarmes')

        self.stdout.write(self.style.SUCCESS(
            f'Pronto: {len(ESCOLAS)} escolas, {len(racks)} pontos, {total_leituras} leituras '
            f'e {total_alarmes} alarmes em {dias} dias.'
        ))
