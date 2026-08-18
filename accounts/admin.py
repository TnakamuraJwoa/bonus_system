from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password

from .forms import CustomLoginForm, UserAccessProfileAdminForm, UserAccessProfileInlineForm
from .models import CustomUser, LoginHistory, UserAccessProfile


class CustomUserResource(resources.ModelResource):

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
        )
        import_id_fields = ("username",)
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        password = row.get("password")

        if password:
            password = str(password).strip()

            if not password.startswith(("pbkdf2_", "argon2$", "bcrypt")):
                row["password"] = make_password(password)


USER_ACCESS_FIELDSETS = (
    (
        "画面の閲覧",
        {
            "fields": ("allow_all_menus",),
            "description": "「全メニューを許可」をオフにすると、下のグループから閲覧可能な画面を選択できます。",
        },
    ),
    ("会員", {"fields": ("menu_group_users",)}),
    ("注文", {"fields": ("menu_group_orders",)}),
    ("ボーナス検索", {"fields": ("menu_group_bonus_search",)}),
    ("ボーナス計算", {"fields": ("menu_group_bonus_calc",)}),
    ("業績検索", {"fields": ("menu_group_business_search",)}),
    ("設定・マスタ", {"fields": ("menu_group_settings",)}),
    (
        "操作権限",
        {
            "fields": (
                "can_create",
                "can_update",
                "can_delete",
                "can_execute",
                "can_export",
            ),
        },
    ),
)


class UserAccessProfileInline(admin.StackedInline):
    model = UserAccessProfile
    form = UserAccessProfileInlineForm
    can_delete = False
    extra = 0
    fieldsets = USER_ACCESS_FIELDSETS
    verbose_name = "操作権限"
    verbose_name_plural = "操作権限（画面・操作を細かく設定）"

    class Media:
        css = {"all": ("css/admin_user_access.css",)}


@admin.register(UserAccessProfile)
class UserAccessProfileAdmin(admin.ModelAdmin):
    form = UserAccessProfileAdminForm
    list_display = (
        "user",
        "menu_permissions_summary",
        "can_create",
        "can_update",
        "can_delete",
        "can_execute",
        "can_export",
    )
    list_filter = (
        "can_create",
        "can_update",
        "can_delete",
        "can_execute",
        "can_export",
    )
    search_fields = ("user__username",)
    fieldsets = (
        (None, {"fields": ("user",)}),
    ) + USER_ACCESS_FIELDSETS

    class Media:
        css = {"all": ("css/admin_user_access.css",)}

    @admin.display(description="閲覧画面")
    def menu_permissions_summary(self, obj):
        if obj.menu_permissions is None:
            return "全画面"
        count = len(obj.menu_permissions)
        return f"{count} 画面"


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "username",
        "event_type",
        "ip_address",
        "request_path",
    )
    list_filter = ("event_type", "occurred_at")
    search_fields = ("username", "ip_address", "request_path", "user_agent")
    date_hierarchy = "occurred_at"
    readonly_fields = (
        "user",
        "username",
        "event_type",
        "occurred_at",
        "ip_address",
        "user_agent",
        "session_key",
        "request_path",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CustomUserAdmin(ImportExportModelAdmin, UserAdmin):
    resource_class = CustomUserResource
    inlines = (UserAccessProfileInline,)


admin.site.register(CustomUser, CustomUserAdmin)

admin.site.site_header = "Bonus System 管理"
admin.site.site_title = "Bonus System"
admin.site.index_title = "管理サイト"
