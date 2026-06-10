from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password

from .models import CustomUser


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


class CustomUserAdmin(ImportExportModelAdmin, UserAdmin):
    resource_class = CustomUserResource


admin.site.register(CustomUser, CustomUserAdmin)