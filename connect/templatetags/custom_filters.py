from django import template
from django.urls import reverse

register = template.Library()


INDIVIDUAL_BONUS_URL_PAIRS = {
    "drive_bonus": ("drive_bonus", "s_drive_bonus"),
    "s_drive_bonus": ("drive_bonus", "s_drive_bonus"),
    "basic_bonus": ("basic_bonus", "s_basic_bonus"),
    "s_basic_bonus": ("basic_bonus", "s_basic_bonus"),
    "matching_bonus": ("matching_bonus", "s_matching_bonus"),
    "s_matching_bonus": ("matching_bonus", "s_matching_bonus"),
    "title_bonus": ("title_bonus", "s_title_bonus"),
    "s_title_bonus": ("title_bonus", "s_title_bonus"),
    "title_diff_bonus": ("title_diff_bonus", "s_title_diff_bonus"),
    "s_title_diff_bonus": ("title_diff_bonus", "s_title_diff_bonus"),
    "repurchase_over_bonus": ("repurchase_over_bonus", "s_repurchase_over_bonus"),
    "s_repurchase_over_bonus": ("repurchase_over_bonus", "s_repurchase_over_bonus"),
    "three_star_global_bonus": ("three_star_global_bonus", "s_three_star_global_bonus"),
    "s_three_star_global_bonus": ("three_star_global_bonus", "s_three_star_global_bonus"),
}

TOTAL_BONUS_URL_PAIRS = {
    "week_bonus": ("week_bonus", "s_week_bonus"),
    "s_week_bonus": ("week_bonus", "s_week_bonus"),
    "month_bonus": ("month_bonus", "s_month_bonus"),
    "s_month_bonus": ("month_bonus", "s_month_bonus"),
}


@register.simple_tag
def paired_bonus_url(current_url_name, target_mode, bonus_group):
    pair_index = 1 if target_mode == "search" else 0

    if bonus_group == "total":
        url_name = TOTAL_BONUS_URL_PAIRS.get(
            current_url_name,
            ("week_bonus", "s_week_bonus"),
        )[pair_index]
    else:
        url_name = INDIVIDUAL_BONUS_URL_PAIRS.get(
            current_url_name,
            ("drive_bonus", "s_drive_bonus"),
        )[pair_index]

    return reverse(f"connect:{url_name}")

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
