from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin

from .models import CustomUser
from .models import CustomUser



class CustomUserResource(resources.ModelResource):
    def before_import_row(self, row, **kwargs):
        if 'password' in row:
            value = row['password']
            row['password'] = make_password(value)
        else:
            # 'password'フィールドがない場合は何もせずにスキップする
            pass
    # Modelに対するdjango-import-exportの設定
    class Meta:
        model = CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ImportExportModelAdmin):
    list_display = (
        "username",
        "email",
        "vip_male_price",
        "vip_female_price",
        "gender",
        "account_type",
        "account_code",
        "is_superuser",
        "is_staff",
        "is_active",
    )

    search_fields = ['username', 'email']


    list_per_page = 10

    fieldsets = (
        ('会員情報', {'fields': ('username', 'email', 'password', 'gender', 'account_type', 'account_code')}),
        ('プラン情報', {'fields': ('vip_male_price', 'vip_female_price')}),
        ('権限情報', {'fields': ('groups', 'user_permissions', 'is_staff', 'is_active')}),
    )


    # django-import-exportsの設定
    resource_class = CustomUserResource