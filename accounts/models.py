from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):

    class Meta:
        verbose_name = '会員'
        verbose_name_plural = '会員一覧'

    def __str__(self):
        return self.username


class LoginHistory(models.Model):
    EVENT_LOGIN = "login"
    EVENT_LOGOUT = "logout"
    EVENT_TIMEOUT_LOGOUT = "timeout_logout"

    EVENT_CHOICES = (
        (EVENT_LOGIN, "ログイン"),
        (EVENT_LOGOUT, "ログアウト"),
        (EVENT_TIMEOUT_LOGOUT, "自動ログアウト"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_histories",
        verbose_name="ユーザー",
    )
    username = models.CharField("ユーザー名", max_length=150, db_index=True)
    event_type = models.CharField("イベント種別", max_length=30, choices=EVENT_CHOICES)
    occurred_at = models.DateTimeField("発生日時", default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField("IPアドレス", null=True, blank=True)
    user_agent = models.TextField("ユーザーエージェント", blank=True)
    session_key = models.CharField("セッションキー", max_length=40, blank=True)
    request_path = models.CharField("リクエストパス", max_length=500, blank=True)

    class Meta:
        verbose_name = "ログイン履歴"
        verbose_name_plural = "ログイン履歴"
        ordering = ("-occurred_at", "-id")
        indexes = (
            models.Index(fields=("event_type", "occurred_at")),
            models.Index(fields=("user", "occurred_at")),
        )

    def __str__(self):
        return f"{self.username} {self.get_event_type_display()} {self.occurred_at:%Y-%m-%d %H:%M:%S}"


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
    menu_permissions = models.JSONField(
        "閲覧可能な画面",
        null=True,
        blank=True,
        default=None,
        help_text="未設定（null）の場合は全画面を閲覧できます。リスト指定時は選択した画面のみ。",
    )

    class Meta:
        verbose_name = "操作権限"
        verbose_name_plural = "操作権限"

    def __str__(self):
        return f"{self.user.username} の操作権限"
