from django.contrib import admin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from django.utils.html import format_html


# Register your models here.
from .models import Prefecture, Region, Plan, PlanDate, GenreList, FavoritePlan, Invite


# 都道府県
class PrefectureResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = Prefecture


@admin.register(Prefecture)
class PrefectureAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "name",
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = PrefectureResource


# 地域
class RegionResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = Region


@admin.register(Region)
class RegionAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "name",
        "prefecture",
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = RegionResource


# プラン
class PlanResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = Plan


@admin.register(Plan)
class PlanAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "plan_name",
        "genre_name",
        "user",
        "place",
        "min_age",
        "max_age",
        "gender_limit",
        "male_participants",
        "female_participants",
        "uniform_participants",
        "male_price",
        "female_price",
        "img1",
        "url",
        "is_vip",
        "plan_active",
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = PlanResource


# プラン日程
class PlanDateResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = PlanDate


@admin.register(PlanDate)
class PlanDateAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "plan_name",
        "custum_user",
        "custum_prefecture",
        "custum_place",
        "custum_genre_name",
        "custum_min_age",
        "custum_max_age",
        "custum_gender_limit",
        "start_time",
        "end_time",
        "custum_is_vip",
        "custum_plan_active",
    )

    list_per_page = 10
    ordering = ('start_time',)  # start_timeを昇順で並べ替える

    def custum_is_vip(self, obj):
        if obj.plan_name.is_vip:
            return format_html('<img src="{}" line-height="16px"/>', '/static/imgs/icons/icon-yes.svg')
        else:
            return format_html('<img src="{}" line-height="16px"/>', '/static/imgs/icons/icon-no.svg')
    custum_is_vip.short_description = 'vip'

    def custum_plan_active(self, obj):
        if obj.plan_name.plan_active:
            return format_html('<img src="{}" line-height="16px"/>', '/static/imgs/icons/icon-yes.svg')
        else:
            return format_html('<img src="{}" line-height="16px"/>', '/static/imgs/icons/icon-no.svg')
    custum_plan_active.short_description = 'アクティブ'

    def custum_gender_limit(self, obj):
        return obj.plan_name.get_gender_limit_display()
    custum_gender_limit.short_description = '性別制限'

    def custum_max_age(self, obj):
        return obj.plan_name.max_age
    custum_max_age.short_description = '最高年齢'

    def custum_min_age(self, obj):
        return obj.plan_name.min_age
    custum_min_age.short_description = '最低年齢'

    def custum_user(self, obj):
        return obj.plan_name.user.username
    custum_user.short_description = 'ユーザー'

    def custum_prefecture(self, obj):
        return obj.plan_name.place.prefecture.name
    custum_prefecture.short_description = '都道府県'

    def custum_genre_name(self, obj):
        return obj.plan_name.genre_name.genre_name
    custum_genre_name.short_description = 'ジャンル名'

    def custum_place(self, obj):
        return obj.plan_name.place
    custum_place.short_description = '地域名'

    # django-import-exportsの設定
    resource_class = PlanDateResource


# イベント一覧
class GenreListResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = GenreList


@admin.register(GenreList)
class GenreListAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "genre_name",
        "text",
        "img",
        "is_hidden",
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = GenreListResource


# お気に入りプラン
class FavoritePlanResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = FavoritePlan


@admin.register(FavoritePlan)
class GenreListAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "plan_date",
        "username",
    )

    fieldsets = (
        ('お気に入り情報 - 追加 - 情報', {'fields': ('username', 'plan_date')}),
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = FavoritePlanResource

# お気に入りプラン
class InviteResource(resources.ModelResource):
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = Invite


#紹介者情報一覧
@admin.register(Invite)
class InviteAdmin(ImportExportModelAdmin):
    # ImportExportModelAdminを利用するようにする
    list_display = (
        "inviting_user",
        "invited_user",
    )

    list_per_page = 10

    # django-import-exportsの設定
    resource_class = InviteResource