from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):

    class Meta:
        verbose_name = '会員'
        verbose_name_plural = '会員一覧'

    def __str__(self):
        return self.username


class UserAccessProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="access_profile",
        verbose_name="ユーザー",
    )
    can_create = models.BooleanField("登録・追加", default=False)
    can_update = models.BooleanField("変更・更新", default=False)
    can_delete = models.BooleanField("削除", default=False)
    can_execute = models.BooleanField("実行（ボーナス計算・一括登録など）", default=False)
    can_export = models.BooleanField("Excel出力", default=False)

    class Meta:
        verbose_name = "操作権限"
        verbose_name_plural = "操作権限"

    def __str__(self):
        return f"{self.user.username} の操作権限"
