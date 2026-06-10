from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):

    class Meta:
        verbose_name = '会員'
        verbose_name_plural = '会員一覧'

    def __str__(self):
        return self.username
