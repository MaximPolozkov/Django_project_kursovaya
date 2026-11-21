from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from users.models import User

MANAGER_GROUP = "Менеджеры"

# Права менеджера: (приложение, кодовое имя права)
MANAGER_PERMISSIONS = [
    ("mailing", "can_view_all_mailings"),
    ("mailing", "can_view_all_recipients"),
    ("mailing", "can_disable_mailing"),
    ("users", "can_view_users"),
    ("users", "can_block_user"),
]


class Command(BaseCommand):
    help = "Создаёт группу «Менеджеры» с нужными правами. --manager EMAIL — сразу добавить в неё пользователя."

    def add_arguments(self, parser):
        parser.add_argument("--manager", metavar="EMAIL", help="Добавить пользователя в менеджеры")

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name=MANAGER_GROUP)
        permissions = []
        for app_label, codename in MANAGER_PERMISSIONS:
            try:
                permissions.append(
                    Permission.objects.get(content_type__app_label=app_label, codename=codename)
                )
            except Permission.DoesNotExist as error:
                raise CommandError(
                    f"Нет права {app_label}.{codename}. Сначала выполните migrate."
                ) from error
        group.permissions.set(permissions)
        status = "создана" if created else "обновлена"
        codes = ", ".join(codename for _, codename in MANAGER_PERMISSIONS)
        self.stdout.write(self.style.SUCCESS(f"Группа «{MANAGER_GROUP}» {status}: {codes}"))

        email = options.get("manager")
        if email:
            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist as error:
                raise CommandError(f"Пользователь {email} не найден.") from error
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"{user.email} добавлен в группу «{MANAGER_GROUP}»"))
