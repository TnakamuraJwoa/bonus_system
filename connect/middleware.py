import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse

from accounts.access import (
    menu_denied_message,
    permission_denied_message,
    required_permission_for_request,
    user_can_access_url,
    user_has_permission,
)


LAST_VISITED_PATH_SESSION_KEY = "last_visited_path"


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
                redirect_path = self._get_redirect_path(request)
                logout(request)
                request.session.flush()
                login_url = reverse("account_login")
                if redirect_path:
                    query = urlencode({"timeout": "1", "next": redirect_path})
                    return redirect(f"{login_url}?{query}")
                return redirect(f"{login_url}?timeout=1")

            request.session["_last_activity"] = now

        return self.get_response(request)

    def _get_redirect_path(self, request):
        if request.method == "GET" and not self._is_exempt(request.path):
            return request.get_full_path()
        return request.session.get(LAST_VISITED_PATH_SESSION_KEY)

    @staticmethod
    def _is_exempt(path):
        return path.startswith(("/accounts/", "/static/", "/media/", "/admin/"))


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
                resolver = getattr(request, "resolver_match", None)
                url_name = resolver.url_name if resolver else None

                if request.method == "GET" and url_name:
                    if not user_can_access_url(request.user, url_name):
                        messages.error(request, menu_denied_message(url_name))
                        return redirect(settings.LOGIN_REDIRECT_URL)

                permission = required_permission_for_request(request)
                if permission and not user_has_permission(request.user, permission):
                    messages.error(request, permission_denied_message(permission))
                    referer = request.META.get("HTTP_REFERER")
                    if referer:
                        return redirect(referer)
                    return redirect(settings.LOGIN_REDIRECT_URL)
        return self.get_response(request)


class LastVisitedPageMiddleware:
    """ログイン後に戻るため、最後に表示した画面をセッションへ保存する。"""

    EXEMPT_PREFIXES = ("/accounts/", "/static/", "/media/", "/admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if self._should_store(request, response):
            request.session[LAST_VISITED_PATH_SESSION_KEY] = request.get_full_path()

        return response

    def _should_store(self, request, response):
        if not request.user.is_authenticated:
            return False
        if request.method != "GET":
            return False
        if response.status_code >= 400:
            return False

        path = request.path
        if path == "/" or path.startswith(self.EXEMPT_PREFIXES):
            return False
        if "/export/" in path or path.rstrip("/").endswith("/export"):
            return False
        if path.rstrip("/").endswith("/template"):
            return False

        return True