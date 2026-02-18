from django import template

register = template.Library()

@register.filter
def is_different_from_previous(value, previous_value):
    print(value+":"+previous_value)
    if value != previous_value:
        return "aaa"
    else:
        return "bbb"