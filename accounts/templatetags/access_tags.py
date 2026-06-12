from django import template

from accounts.menu_registry import bonus_nav_section, nav_group_for_url_name

register = template.Library()


@register.filter
def can_menu(user_access, menu_key):
    if user_access is None:
        return False
    return user_access.can_menu(menu_key)


@register.filter
def has_nav(user_access, nav_key):
    if user_access is None:
        return False
    return user_access.has_nav(nav_key)


@register.filter
def any_menu_in_group(user_access, group_id):
    if user_access is None:
        return False
    return user_access.any_menu_in_group(group_id)


@register.simple_tag(takes_context=True)
def nav_group_active(context, nav_key):
    request = context.get("request")
    if not request or not getattr(request, "resolver_match", None):
        return False
    return nav_group_for_url_name(request.resolver_match.url_name) == nav_key


@register.simple_tag(takes_context=True)
def bonus_dropdown_active(context, nav_key, section):
    request = context.get("request")
    if not request or not getattr(request, "resolver_match", None):
        return False
    url_name = request.resolver_match.url_name
    if nav_group_for_url_name(url_name) != nav_key:
        return False
    return bonus_nav_section(url_name) == section
