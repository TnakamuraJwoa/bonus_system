from urllib.parse import urlsplit

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.access import user_can_access_url


LAST_VISITED_PATH_SESSION_KEY = "last_visited_path"


class LastVisitedAccountAdapter(DefaultAccountAdapter):
    """ログイン成功後、最後に表示した画面へ戻す。"""

    def get_login_redirect_url(self, request):
        last_path = request.session.pop(LAST_VISITED_PATH_SESSION_KEY, None)
        if self._can_redirect_to_path(request, last_path):
            return last_path

        return reverse(settings.LOGIN_REDIRECT_URL)

    def _can_redirect_to_path(self, request, path):
        if not path:
            return False
        if not url_has_allowed_host_and_scheme(
            path,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return False

        parsed = urlsplit(path)
        if self._is_exempt_path(parsed.path):
            return False

        try:
            match = resolve(parsed.path)
        except Resolver404:
            return False

        return user_can_access_url(request.user, match.url_name)

    @staticmethod
    def _is_exempt_path(path):
        return (
            path == "/"
            or path.startswith("/accounts/")
            or path.startswith("/static/")
            or path.startswith("/media/")
            or path.startswith("/admin/")
            or "/export/" in path
            or path.rstrip("/").endswith("/export")
            or path.rstrip("/").endswith("/template")
        )
