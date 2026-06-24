from dataclasses import dataclass, field

from accounts.menu_registry import (
    ALL_MENU_KEYS,
    GROUP_MENU_KEYS,
    NAV_GROUP_MAP,
    menu_key_for_url_name,
)

PERM_CREATE = "can_create"
PERM_UPDATE = "can_update"
PERM_DELETE = "can_delete"
PERM_EXECUTE = "can_execute"
PERM_EXPORT = "can_export"

ALL_PERMISSIONS = (
    PERM_CREATE,
    PERM_UPDATE,
    PERM_DELETE,
    PERM_EXECUTE,
    PERM_EXPORT,
)

EXECUTE_ACTIONS = {
    "register_drive_bonus",
    "register_basic_bonus",
    "register_matching_bonus",
    "register_title_bonus",
    "register_title_diff_bonus",
    "repurchase_over_bonus",
    "register_three_star_global_bonus",
    "three_star_global_bonus",
    "register_week_bonus",
    "register_month_title",
    "register_month_bonus",
    "copy",
}

MUTATING_POST_PATHS = {
    "/title_registration/",
    "/user_target_rank/",
    "/repurchase_last_month/",
}

PERMISSION_LABELS = {
    PERM_CREATE: "登録・追加",
    PERM_UPDATE: "変更・更新",
    PERM_DELETE: "削除",
    PERM_EXECUTE: "実行（ボーナス計算・一括登録など）",
    PERM_EXPORT: "Excel出力",
}

EXEMPT_MENU_URL_NAMES = {
    "index",
    "inquiry",
}


@dataclass(frozen=True)
class UserAccess:
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False
    can_execute: bool = False
    can_export: bool = False
    menu_permissions: tuple = field(default_factory=tuple)
    all_menus_allowed: bool = True

    @property
    def is_view_only(self):
        return not any(
            (
                self.can_create,
                self.can_update,
                self.can_delete,
                self.can_execute,
                self.can_export,
            )
        )

    def has(self, permission):
        return bool(getattr(self, permission, False))

    def can_menu(self, menu_key):
        if self.all_menus_allowed:
            return True
        return menu_key in self.menu_permissions

    def has_nav(self, nav_key):
        group = NAV_GROUP_MAP.get(nav_key)
        if not group:
            return self.can_menu(nav_key)
        return self.any_menu_in_group(group)

    def any_menu_in_group(self, group_id):
        if self.all_menus_allowed:
            return True
        keys = GROUP_MENU_KEYS.get(group_id, ())
        return any(key in self.menu_permissions for key in keys)


def full_access():
    return UserAccess(True, True, True, True, True, ALL_MENU_KEYS, True)


def get_user_access(user):
    if not user.is_authenticated:
        return UserAccess()

    if user.is_superuser:
        return full_access()

    profile = getattr(user, "access_profile", None)
    if profile is None:
        if user.is_staff:
            return full_access()
        return UserAccess()

    raw_menus = profile.menu_permissions
    if raw_menus is None:
        return UserAccess(
            can_create=profile.can_create,
            can_update=profile.can_update,
            can_delete=profile.can_delete,
            can_execute=profile.can_execute,
            can_export=profile.can_export,
            menu_permissions=ALL_MENU_KEYS,
            all_menus_allowed=True,
        )

    enabled = tuple(sorted(set(raw_menus)))
    return UserAccess(
        can_create=profile.can_create,
        can_update=profile.can_update,
        can_delete=profile.can_delete,
        can_execute=profile.can_execute,
        can_export=profile.can_export,
        menu_permissions=enabled,
        all_menus_allowed=False,
    )


def user_has_permission(user, permission):
    return get_user_access(user).has(permission)


def user_can_access_url(user, url_name):
    if url_name in EXEMPT_MENU_URL_NAMES:
        return True

    menu_key = menu_key_for_url_name(url_name)
    if menu_key is None:
        return True

    return get_user_access(user).can_menu(menu_key)


def required_permission_for_request(request):
    path = request.path

    if request.method == "GET":
        if "/export/" in path or path.rstrip("/").endswith("/export"):
            return PERM_EXPORT
        return None

    if request.method != "POST":
        return None

    if request.POST.get("export") == "excel":
        return PERM_EXPORT

    action = (request.POST.get("action") or "").strip()
    if action in ("create", "manual_create"):
        return PERM_CREATE
    if action == "update":
        return PERM_UPDATE
    if action == "delete":
        return PERM_DELETE
    if action in EXECUTE_ACTIONS or action.startswith("register_"):
        return PERM_EXECUTE

    if not action and path in MUTATING_POST_PATHS:
        return PERM_EXECUTE

    if action:
        return PERM_EXECUTE

    return None


def permission_denied_message(permission):
    label = PERMISSION_LABELS.get(permission, "操作")
    return f"権限がありません（{label}）。"


def menu_denied_message(menu_key):
    return "権限がありません（この画面は閲覧できません）。"
