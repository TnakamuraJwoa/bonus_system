import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse

from accounts.access import (
    permission_denied_message,
    required_permission_for_request,
    user_has_permission,
)


class SessionIdleTimeoutMiddleware:
    """1時間操作がなければ自動ログアウトする。"""

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 3600)

    def __call__(self, request):
        if request.user.is_authenticated and not self._is_exempt(request.path):
            now = time.time()
            last_activity = request.session.get("_last_activity")

            if last_activity is not None and (now - last_activity) > self.timeout:
                logout(request)
                request.session.flush()
                login_url = reverse("account_login")
                return redirect(f"{login_url}?timeout=1")

            request.session["_last_activity"] = now

        return self.get_response(request)

    @staticmethod
    def _is_exempt(path):
        return path.startswith("/static/") or path.startswith("/media/")


class LoginRequiredMiddleware:
    EXEMPT_PREFIXES = ("/accounts/", "/static/", "/media/", "/admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            if path == "/" or path.startswith(self.EXEMPT_PREFIXES):
                return self.get_response(request)
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)


class UserPermissionMiddleware:
    EXEMPT_PREFIXES = ("/accounts/", "/static/", "/media/", "/admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path
            if path != "/" and not path.startswith(self.EXEMPT_PREFIXES):
                permission = required_permission_for_request(request)
                if permission and not user_has_permission(request.user, permission):
                    messages.error(request, permission_denied_message(permission))
                    referer = request.META.get("HTTP_REFERER")
                    if referer:
                        return redirect(referer)
                    return redirect(settings.LOGIN_REDIRECT_URL)
        return self.get_response(request)