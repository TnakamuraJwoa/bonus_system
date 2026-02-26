from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
# Create your models here.

class Prefecture(models.Model):
    name = models.CharField(max_length=50, verbose_name='都道府県名', unique=True)

    class Meta:
        verbose_name = '都道府県'
        verbose_name_plural = '都道府県'

    def __str__(self):
        return self.name


class Region(models.Model):
    name = models.CharField(max_length=50, verbose_name='地域名')
    prefecture = models.ForeignKey(Prefecture, on_delete=models.CASCADE, related_name='regions', verbose_name='都道府県')

    class Meta:
        verbose_name = '地域'
        verbose_name_plural = '地域'

    def __str__(self):
        return self.name


class GenreList(models.Model):
    genre_name = models.CharField(max_length=50, verbose_name='ジャンル名')
    text = models.CharField(max_length=50, verbose_name='テキスト')
    img = models.ImageField(upload_to='images/', verbose_name='画像', blank=True, null=True)
    is_hidden = models.BooleanField('非表示', default=False)

    class Meta:
        verbose_name = 'ジャンル一覧'
        verbose_name_plural = 'ジャンル一覧'

    def __str__(self):
        return self.genre_name


class Plan(models.Model):
    MALE = 'M'
    FEMALE = 'F'
    OTHER = 'O'

    GENDER_CHOICES = [
        (MALE, '男性'),
        (FEMALE, '女性'),
        (OTHER, 'その他'),
    ]

    plan_name = models.CharField(max_length=50, verbose_name='プラン名')
    genre_name = models.ForeignKey(GenreList, on_delete=models.CASCADE, verbose_name='ジャンル名')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='ユーザー')
    description = models.TextField('説明', default="", blank=True)
    place = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='plans', verbose_name='地域名')
    min_age = models.IntegerField(verbose_name='最低年齢', default=None, blank=True, null=True)
    max_age = models.IntegerField(verbose_name='最高年齢', default=None, blank=True, null=True)
    gender_limit = models.CharField(verbose_name='性別制限', choices=GENDER_CHOICES, default=OTHER)
    male_participants = models.IntegerField('男性人数', default=0)
    female_participants = models.IntegerField('女性人数', default=0)
    uniform_participants = models.IntegerField('一律人数', default=0)
    male_price = models.IntegerField('男性料金', default=0)
    female_price = models.IntegerField('女性料金', default=0)
    img1 = models.ImageField(upload_to='images/', verbose_name='画像１', blank=True, null=True)
    img2 = models.ImageField(upload_to='images/', verbose_name='画像２', blank=True, null=True)
    img3 = models.ImageField(upload_to='images/', verbose_name='画像３', blank=True, null=True)
    url = models.URLField(verbose_name='URL', blank=True, null=True)
    is_vip = models.BooleanField('vip', default=False)
    plan_active = models.BooleanField('アクティブ', default=False)

    class Meta:
        verbose_name = 'プラン一覧'
        verbose_name_plural = 'プラン一覧'

    def __str__(self):
        return self.plan_name


class PlanDate(models.Model):
    plan_name = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='plan_dates', verbose_name='プラン名')
    start_time = models.DateTimeField(verbose_name='開始時間')
    end_time = models.DateTimeField(verbose_name='終了時間')

    class Meta:
        verbose_name = 'プラン日程'
        verbose_name_plural = 'プラン日程'

    def __str__(self):
        return str(self.plan_name.user) + ": " + str(self.plan_name)


class FavoritePlan(models.Model):
    username = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='ユーザー')
    plan_date = models.ForeignKey(PlanDate, on_delete=models.CASCADE, related_name='plan_dates', verbose_name='プラン名-日付')

    class Meta:
        verbose_name = 'お気に入りプラン'
        verbose_name_plural = 'お気に入りプラン'

    def __str__(self):
        return self.plan_date

class Invite(models.Model):
    inviting_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invites_sent', verbose_name='招待するユーザー')
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invites_received', verbose_name='招待されるユーザー')

    class Meta:
        verbose_name = '紹介者情報'
        verbose_name_plural = '紹介者情報一覧'

    def __str__(self):
        return self.inviting_user.username



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

    class Meta:
        managed = False                 # ← 既存RDSなので必須
        db_table = "period_master"      # ← 実テーブル名


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


class PrevMonthPurchaseStatus(models.Model):

    year = models.PositiveSmallIntegerField(
        verbose_name="対象年"
    )

    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="対象月(1-12)"
    )

    CREATE_STATUS_CHOICES = (
        (0, "未作成"),
        (1, "作成済"),
    )

    create_status = models.PositiveSmallIntegerField(
        choices=CREATE_STATUS_CHOICES,
        default=0,
        verbose_name="作成状態"
    )

    class Meta:   # ← インデント重要
        db_table = "prev_month_purchase_status"
        managed = False
        unique_together = ("year", "month")

    def __str__(self):
        return f"{self.year}-{self.month:02d}"