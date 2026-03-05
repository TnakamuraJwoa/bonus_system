from django import template

register = template.Library()

@register.filter
def is_different_from_previous(value, previous_value):
    print(value+":"+previous_value)
    if value != previous_value:
        return "aaa"
    else:
        return "bbb"


# ------------------------------
# 追加するフィルタ
# ------------------------------
@register.filter
def get_item(d, key):
    if d is None:
        return ""
    return d.get(key, "")