from .access import get_user_access


def user_access(request):
    return {"user_access": get_user_access(request.user)}
