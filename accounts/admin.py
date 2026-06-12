from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password

from .models import CustomUser, UserAccessProfile


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


class UserAccessProfileInline(admin.StackedInline):
    model = UserAccessProfile
    can_delete = False
    extra = 0
    fields = (
        "can_create",
        "can_update",
        "can_delete",
        "can_execute",
        "can_export",
    )
    verbose_name = "操作権限"
    verbose_name_plural = "操作権限（未チェック＝見るだけ）"


@admin.register(UserAccessProfile)
class UserAccessProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
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


class CustomUserAdmin(ImportExportModelAdmin, UserAdmin):
    resource_class = CustomUserResource
    inlines = (UserAccessProfileInline,)


admin.site.register(CustomUser, CustomUserAdmin)
