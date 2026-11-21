from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from mailing.models import Mailing, Recipient
from mailing.services import HOME_STATS_CACHE_KEY, get_user_stats_cache_key


@receiver(post_save, sender=Mailing)
@receiver(post_delete, sender=Mailing)
def clear_cache_on_mailing_change(sender, instance, **kwargs):
    cache.delete_many([HOME_STATS_CACHE_KEY, get_user_stats_cache_key(instance.owner_id)])


@receiver(post_save, sender=Recipient)
@receiver(post_delete, sender=Recipient)
def clear_cache_on_recipient_change(sender, instance, **kwargs):
    cache.delete(HOME_STATS_CACHE_KEY)


@receiver(m2m_changed, sender=Mailing.recipients.through)
def clear_cache_on_recipients_change(sender, instance, **kwargs):
    cache.delete(HOME_STATS_CACHE_KEY)
