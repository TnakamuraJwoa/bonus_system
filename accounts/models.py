from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    # 拡張ユーザモデル
    ACCOUNT_TYPE = (
        (0, '管理者'),
        (1, '一般'),
    )

    GENDER = (
        (0, '女性'),
        (1, '男性'),
    )

    account_type = models.IntegerField('アカウントタイプ', choices=ACCOUNT_TYPE, null=True, blank=True)
    gender = models.IntegerField('性別', choices=GENDER, null=True, blank=True)
    account_code = models.CharField(max_length=15, verbose_name='アカウントコード', unique=True)
    vip_male_price = models.IntegerField('VIP男性料金', default=0)
    vip_female_price = models.IntegerField('VIP女性料金', default=0)

    class Meta:
        verbose_name = '会員'
        verbose_name_plural = '会員一覧'

    def __str__(self):
        return self.username
