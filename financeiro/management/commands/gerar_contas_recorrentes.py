from django.core.management.base import BaseCommand, CommandError

from core.periodo import dia_local_atual
from financeiro.services.recorrentes import gerar_competencia


class Command(BaseCommand):
    help = (
        "Gera contas a pagar a partir das recorrências ativas "
        "para a competência informada (mês atual se omitido)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--mes", type=int, help="Mês da competência (1-12).")
        parser.add_argument("--ano", type=int, help="Ano da competência.")

    def handle(self, *args, **options):
        hoje = dia_local_atual()
        mes = options["mes"] if options["mes"] is not None else hoje.month
        ano = options["ano"] if options["ano"] is not None else hoje.year
        if mes < 1 or mes > 12:
            raise CommandError("Informe um mês entre 1 e 12.")
        if ano < 2000 or ano > 2100:
            raise CommandError("Informe um ano válido.")

        resumo = gerar_competencia(mes, ano)
        self.stdout.write(
            f"Competência {mes:02d}/{ano}: "
            f"{resumo.criadas} criadas, "
            f"{resumo.existentes} já existentes, "
            f"{resumo.inativas} inativas, "
            f"{resumo.fora_vigencia} fora da vigência, "
            f"{len(resumo.erros)} com erro."
        )
        for erro in resumo.erros:
            self.stderr.write(f"- {erro.descricao}: {erro.motivo}")
