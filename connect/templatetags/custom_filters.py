from datetime import date, datetime

from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


def _to_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue

    return None


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


@register.filter
def jp_date(value):
    parsed = _to_date(value)
    if not parsed:
        return value if value not in (None, "") else ""
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


@register.simple_tag
def jp_date_range(start, end):
    start_text = jp_date(start)
    end_text = jp_date(end)
    if start_text and end_text:
        return f"{start_text} ～ {end_text}"
    return start_text or end_text or ""


@register.filter
def jp_year_month(value):
    if not value:
        return ""

    text = str(value).strip()
    if len(text) >= 6:
        year = text[:4]
        month = int(text[4:6])
        return f"{year}年{month}月"

    return text


@register.simple_tag
def jp_year_month_label(year, month):
    if year in (None, "") or month in (None, ""):
        return ""
    return f"{int(year)}年{int(month)}月"


@register.inclusion_tag("com/_selection_indicator.html")
def selection_from_period(period, empty_message=""):
    if not period:
        return {
            "kibetu": None,
            "date_text": None,
            "empty_message": empty_message or None,
        }

    kibetu = getattr(period, "kibetu", None)
    payment = getattr(period, "payment_date", None)

    if payment:
        date_text = jp_date(payment)
    else:
        start_text = jp_date(getattr(period, "st_date", None))
        end_text = jp_date(getattr(period, "end_date", None))
        if start_text and end_text:
            date_text = f"{start_text} ～ {end_text}"
        else:
            date_text = start_text or end_text or None

    return {
        "kibetu": kibetu,
        "date_text": date_text,
        "empty_message": None,
    }


@register.simple_tag(takes_context=True)
def sortable_th(context, column, label):
    request = context.get("request")
    sort = context.get("sort", "")
    direction = context.get("direction", "asc")
    next_direction = context.get("next_direction", "desc")

    if not request:
        return format_html('<th class="text-center">{}</th>', label)

    params = request.GET.copy()
    params["sort"] = column
    if sort == column:
        params["direction"] = next_direction
    else:
        params["direction"] = "asc"

    indicator = ""
    if sort == column:
        indicator = " ▲" if direction == "asc" else " ▼"

    return format_html(
        '<th class="text-center sortable-th">'
        '<a href="?{}" class="sortable-th__link text-dark text-decoration-none">'
        "{}{}</a></th>",
        params.urlencode(),
        label,
        indicator,
    )
