from django.db import models
# Create your models here.


class TitleMaster(models.Model):
    title_id = models.PositiveIntegerField(primary_key=True)
    title_name = models.CharField(max_length=100)

    class Meta:
        managed = False              # ← 既存RDSテーブルなので必須
        db_table = "title_master"    # ← MySQLの実テーブル名


class PeriodMaster(models.Model):
    kibetu = models.CharField(
        max_length=20,
        primary_key=True
    )
    st_date = models.DateField(
        null=True,
        blank=True
    )
    end_date = models.DateField(
        null=True,
        blank=True
    )

    payment_date = models.DateField(
        null=True,
        blank=True
    )

    completion_date = models.DateField(
        null=True,
        blank=True
    )

    class Meta:
        managed = False                 # ← 既存RDSなので必須
        db_table = "period_master"      # ← 実テーブル名


class MonthlyPeriod(models.Model):
    kibetu = models.CharField(max_length=20, primary_key=True)
    year = models.IntegerField()
    month = models.IntegerField()
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "monthly_period"


class UserTitles(models.Model):
    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(
        "User",
        db_column="user_id",
        on_delete=models.DO_NOTHING,
        related_name="titles",
    )

    title = models.ForeignKey(
        "TitleMaster",
        db_column="title_id",
        on_delete=models.DO_NOTHING,
        related_name="user_titles",
    )

    bonus_period = models.CharField(max_length=8, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "user_titles"


class Orders(models.Model):
    order_code = models.CharField(
        max_length=255,
        primary_key=True
    )
    #注文状況
    order_status = models.IntegerField(null=True, blank=True)
    #JWOA会員ID
    jwoa_code = models.CharField(max_length=255, null=True, blank=True)
    #注文者_氏名
    order_name = models.CharField(max_length=255, null=True, blank=True)
    #注文区分
    order_type = models.IntegerField(null=True, blank=True)
    order_option = models.IntegerField(null=True, blank=True)
    #注文日時
    order_at = models.DateTimeField(null=True, blank=True)
    deposit_at = models.DateTimeField(null=True, blank=True)
    #入金日時
    bv_actived_at = models.DateTimeField(null=True, blank=True)
    #BV反映FLG
    bv_actived_flg = models.BooleanField(default=False)
    total_bv = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "orders"


class User(models.Model):
    id = models.AutoField(primary_key=True)

    jmoa_code = models.CharField(
        max_length=255,
        db_column="jmoa_code",
        verbose_name="JMOA会員ID"
    )

    introducer_code = models.CharField(
        max_length=255,
        db_column="introducer_code",
        verbose_name="紹介者ID",
        blank=True,
        null=True
    )

    placement_code = models.CharField(
        max_length=255,
        db_column="placement_code",
        verbose_name="上位者ID",
        blank=True,
        null=True
    )

    group_code = models.CharField(
        max_length=255,
        db_column="group_code",
        verbose_name="会員グループID",
        blank=True,
        null=True
    )

    send_bv_name = models.CharField(
        max_length=255,
        db_column="send_bv_name",
        verbose_name="BV反映用氏名",
        blank=True,
        null=True
    )

    status_code = models.IntegerField(
        default=1,
        db_column="status_code",
        verbose_name="ステータス"
    )

    rank = models.IntegerField(
        default=9,
        db_column="rank",
        verbose_name="会員ランク"
    )

    salon_administrator = models.IntegerField(
        default=2,
        db_column="salon_administrator",
        verbose_name="サロン判定"
    )

    salon_name = models.CharField(
        max_length=255,
        db_column="salon_name",
        verbose_name="サロン名",
        blank=True,
        null=True
    )

    interim_at = models.DateTimeField(
        db_column="interim_at",
        blank=True,
        null=True
    )

    activated_at = models.DateTimeField(
        db_column="activated_at",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        db_column="created_at",
        blank=True,
        null=True
    )

    class Meta:
        db_table = "users"
        managed = False  # ← 既存テーブルなので重要
        verbose_name = "会員"
        verbose_name_plural = "会員一覧"

    def __str__(self):
        return self.jmoa_code


class PurchaseInfoList(models.Model):

    id = models.BigAutoField(primary_key=True)

    year = models.PositiveSmallIntegerField(
        verbose_name="対象年"
    )

    month = models.PositiveSmallIntegerField(
        verbose_name="対象月(1-12)"
    )

    jwoa_code = models.CharField(
        max_length=16,
        verbose_name="会員コード"
    )

    send_bv_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="会員名(表示用)"
    )

    bv = models.PositiveIntegerField(
        verbose_name="BV(合計)"
    )

    created_at = models.DateTimeField(
        verbose_name="作成日時"
    )

    updated_at = models.DateTimeField(
        verbose_name="更新日時"
    )

    class Meta:
        db_table = "purchase_info_list"
        managed = False  # ← 既存テーブルを使うので重要
        verbose_name = "購入情報登録"
        verbose_name_plural = "購入情報登録"

        constraints = [
            models.UniqueConstraint(
                fields=["year", "month", "jwoa_code"],
                name="uq_purchase_info_ym_user"
            )
        ]

    def __str__(self):
        return f"{self.year}-{self.month} {self.jwoa_code} ({self.bv})"


class Settings(models.Model):

    name = models.CharField(
        max_length=50,
        verbose_name="設定キー"
    )

    value = models.CharField(
        max_length=100,
        verbose_name="値"
    )

    comment = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="説明"
    )

    class Meta:
        db_table = "settings"
        verbose_name = "設定"
        verbose_name_plural = "設定"