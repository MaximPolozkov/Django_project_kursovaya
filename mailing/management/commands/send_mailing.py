from django.core.management.base import BaseCommand, CommandError

from mailing.models import Mailing
from mailing.services import MailingSendError, send_mailing


class Command(BaseCommand):
    help = (
        "Запускает рассылку из командной строки: "
        "send_mailing <id> — одну рассылку, send_mailing --all — все, которые сейчас можно отправить."
    )

    def add_arguments(self, parser):
        parser.add_argument("mailing_id", nargs="?", type=int, help="ID рассылки")
        parser.add_argument(
            "--all", action="store_true", help="Отправить все включённые рассылки, у которых сейчас период отправки"
        )

    def handle(self, *args, **options):
        if options["all"]:
            Mailing.update_all_statuses()
            mailings = Mailing.objects.filter(
                status=Mailing.Status.STARTED, is_active=True
            ).select_related("message")
            if not mailings:
                self.stdout.write("Сейчас нет рассылок, которые можно отправить.")
                return
        elif options["mailing_id"]:
            try:
                mailings = [Mailing.objects.select_related("message").get(pk=options["mailing_id"])]
            except Mailing.DoesNotExist as error:
                raise CommandError(f"Рассылка №{options['mailing_id']} не найдена.") from error
        else:
            raise CommandError("Укажите ID рассылки или флаг --all.")

        for mailing in mailings:
            try:
                success, failure = send_mailing(mailing)
            except MailingSendError as error:
                self.stdout.write(self.style.ERROR(f"Рассылка №{mailing.pk}: {error}"))
            else:
                style = self.style.SUCCESS if not failure else self.style.WARNING
                self.stdout.write(
                    style(f"Рассылка №{mailing.pk}: успешно — {success}, с ошибкой — {failure}")
                )
