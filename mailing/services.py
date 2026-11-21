import smtplib

from django.conf import settings
from django.core.cache import cache
from django.core.mail import BadHeaderError, send_mail
from django.db.models import Count, Q
from django.utils import timezone

from mailing.models import Mailing, MailingAttempt, Recipient

HOME_STATS_CACHE_KEY = "home_stats"


def get_user_stats_cache_key(user_id):
    return f"user_stats_{user_id}"


class MailingSendError(Exception):
    """Рассылку нельзя запустить (не то время, отключена, нет получателей)."""


def send_mailing(mailing):
    """Отправляет письмо рассылки всем её получателям и сохраняет попытки.

    Возвращает (успешно, не успешно). Если запуск запрещён — MailingSendError.
    """
    mailing.update_status()

    if not mailing.is_active:
        raise MailingSendError("Рассылка отключена менеджером — запустить её нельзя.")

    now = timezone.now()
    if not (mailing.start_time <= now <= mailing.end_time):
        start = timezone.localtime(mailing.start_time).strftime("%d.%m.%Y %H:%M")
        end = timezone.localtime(mailing.end_time).strftime("%d.%m.%Y %H:%M")
        raise MailingSendError(
            f"Сейчас рассылку запустить нельзя: отправка разрешена с {start} по {end}."
        )

    recipients = list(mailing.recipients.all())
    if not recipients:
        raise MailingSendError("У рассылки нет получателей.")

    success_count = 0
    failure_count = 0
    for recipient in recipients:
        try:
            sent = send_mail(
                subject=mailing.message.subject,
                message=mailing.message.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
        except (smtplib.SMTPException, BadHeaderError, OSError) as error:
            status = MailingAttempt.Status.FAILURE
            response = f"{error.__class__.__name__}: {error}"
        else:
            if sent:
                status = MailingAttempt.Status.SUCCESS
                response = f"Письмо принято почтовым сервером для {recipient.email}"
            else:
                status = MailingAttempt.Status.FAILURE
                response = "Почтовый сервер не принял письмо"

        MailingAttempt.objects.create(
            mailing=mailing,
            recipient=recipient,
            status=status,
            server_response=response,
        )
        if status == MailingAttempt.Status.SUCCESS:
            success_count += 1
        else:
            failure_count += 1

    cache.delete(get_user_stats_cache_key(mailing.owner_id))
    return success_count, failure_count


def get_home_stats():
    """Показатели главной страницы. Кешируются на CACHE_TTL секунд."""
    stats = cache.get(HOME_STATS_CACHE_KEY)
    if stats is None:
        Mailing.update_all_statuses()
        now = timezone.now()
        stats = {
            "total_mailings": Mailing.objects.count(),
            "active_mailings": Mailing.objects.filter(
                status=Mailing.Status.STARTED,
                start_time__lte=now,
                end_time__gte=now,
                is_active=True,
            ).count(),
            "unique_recipients": Recipient.objects.values("email").distinct().count(),
        }
        cache.set(HOME_STATS_CACHE_KEY, stats, settings.CACHE_TTL)
    return stats


def get_user_stats(user):
    """Статистика попыток по рассылкам пользователя. Кешируется на CACHE_TTL секунд."""
    key = get_user_stats_cache_key(user.pk)
    stats = cache.get(key)
    if stats is None:
        success = Q(attempts__status=MailingAttempt.Status.SUCCESS)
        failure = Q(attempts__status=MailingAttempt.Status.FAILURE)
        mailings = (
            Mailing.objects.filter(owner=user)
            .select_related("message")
            .annotate(
                success_count=Count("attempts", filter=success),
                failure_count=Count("attempts", filter=failure),
            )
            .order_by("-created_at")
        )
        rows = [
            {
                "pk": mailing.pk,
                "subject": mailing.message.subject,
                "status": mailing.get_status_display(),
                "success": mailing.success_count,
                "failure": mailing.failure_count,
            }
            for mailing in mailings
        ]
        total_success = sum(row["success"] for row in rows)
        total_failure = sum(row["failure"] for row in rows)
        stats = {
            "total_attempts": total_success + total_failure,
            "success_attempts": total_success,
            "failure_attempts": total_failure,
            # Каждая успешная попытка — одно отправленное письмо
            "messages_sent": total_success,
            "mailings": rows,
        }
        cache.set(key, stats, settings.CACHE_TTL)
    return stats
