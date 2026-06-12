from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomUser, UserAccessProfile


@receiver(post_save, sender=CustomUser)
def create_user_access_profile(sender, instance, created, **kwargs):
    if created:
        UserAccessProfile.objects.get_or_create(user=instance)
