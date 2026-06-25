from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_save
from django.dispatch import receiver

from .login_history import record_login_history
from .models import CustomUser, LoginHistory, UserAccessProfile


@receiver(post_save, sender=CustomUser)
def create_user_access_profile(sender, instance, created, **kwargs):
    if created:
        UserAccessProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def record_user_logged_in(sender, request, user, **kwargs):
    record_login_history(request, user, LoginHistory.EVENT_LOGIN)


@receiver(user_logged_out)
def record_user_logged_out(sender, request, user, **kwargs):
    if getattr(request, "_skip_login_history_logout", False):
        return
    record_login_history(request, user, LoginHistory.EVENT_LOGOUT)
