from datetime import date, datetime, timezone as datetime_timezone

from django import template
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from connect.bonus_help import get_bonus_help
from connect.business_search_registration import parse_kibetu_list
from connect.models import MonthlyPeriod, PeriodMaster

register = template.Library()


@register.filter
def jst_datetime(value):
    """Convert datetime values from UTC to the configured Japan timezone."""
    if value is None or value == "":
        return value
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, datetime_timezone.utc)
        return timezone.localtime(value, timezone.get_default_timezone())
    return value


def _to_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return jst_datetime(value).date()
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
    "matching_bonus_tree": ("matching_bonus", "s_matching_bonus"),
    "month_title": ("month_title", "s_month_title"),
    "s_month_title": ("month_title", "s_month_title"),
    "title_bonus": ("title_bonus", "s_title_bonus"),
    "s_title_bonus": ("title_bonus", "s_title_bonus"),
    "title_diff_bonus": ("title_diff_bonus", "s_title_diff_bonus"),
    "s_title_diff_bonus": ("title_diff_bonus", "s_title_diff_bonus"),
    "repurchase_over_bonus": ("repurchase_over_bonus", "s_repurchase_over_bonus"),
    "s_repurchase_over_bonus": ("repurchase_over_bonus", "s_repurchase_over_bonus"),
    "three_star_global_bonus": ("three_star_global_bonus", "s_three_star_global_bonus"),
    "s_three_star_global_bonus": ("three_star_global_bonus", "s_three_star_global_bonus"),
    "global_bonus": ("global_bonus", "s_global_bonus"),
    "s_global_bonus": ("global_bonus", "s_global_bonus"),
}

TOTAL_BONUS_URL_PAIRS = {
    "week_bonus": ("week_bonus", "s_week_bonus"),
    "s_week_bonus": ("week_bonus", "s_week_bonus"),
    "month_bonus": ("month_bonus", "s_month_bonus"),
    "s_month_bonus": ("month_bonus", "s_month_bonus"),
}

BONUS_HISTORY_FIELD_BY_URL_NAME = {
    "drive_bonus": "drive_bonus",
    "basic_bonus": "basic_bonus",
    "matching_bonus": "matching_bonus",
    "week_bonus": "week_bonus",
    "month_title": "month_title",
    "title_bonus": "title_bonus",
    "title_diff_bonus": "title_diff_bonus",
    "repurchase_over_bonus": "repurchase_over_bonus",
    "three_star_global_bonus": "three_star_global_bonus",
    "global_bonus": "global_bonus",
    "month_bonus": "month_bonus",
    "title_registration": "title_registration",
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


@register.simple_tag
def bonus_help(help_key, fallback_title=""):
    return get_bonus_help(help_key, fallback_title)

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
def rank_label(value):
    labels = {
        "1": "シルバー",
        "2": "ゴールド",
        "3": "プラチナ",
        "4": "ダイヤ",
        "9": "一般会員",
    }
    if value in (None, ""):
        return "-"
    key = str(value).strip()
    return labels.get(key, key)


@register.filter
def rank_badge_class(value):
    classes = {
        "1": "badge-secondary",
        "2": "badge-warning",
        "3": "badge-info",
        "4": "badge-primary",
        "9": "badge-light",
    }
    if value in (None, ""):
        return "badge-light"
    key = str(value).strip()
    return classes.get(key, "badge-light")


@register.filter
def member_status_label(value):
    labels = {
        "1": "アクティブ",
        "2": "凍結",
        "3": "退会",
        "4": "中途解約",
        "5": "非アクティブ",
    }
    if value in (None, ""):
        return "-"
    key = str(value).strip()
    return labels.get(key, key)


@register.filter
def member_status_badge_class(value):
    # 稼働中＝緑／一時停止＝黄／解約＝赤／退会・停止＝暗色で状態の重さを表す。
    classes = {
        "1": "badge-success",
        "2": "badge-warning",
        "3": "badge-dark",
        "4": "badge-danger",
        "5": "badge-secondary",
    }
    if value in (None, ""):
        return "badge-light"
    key = str(value).strip()
    return classes.get(key, "badge-light")


@register.filter
def title_badge_class(value):
    """3スターダイヤ(title_id>=6)以上だけ色分けする（青・緑以外）。"""
    classes = {
        "6": "badge-title-orange",
        "7": "badge-title-purple",
        "8": "badge-title-rose",
        "9": "badge-title-amber",
        "10": "badge-title-fuchsia",
        "11": "badge-title-slate",
    }
    if value in (None, ""):
        return ""
    key = str(value).strip()
    try:
        title_id = int(key)
    except (TypeError, ValueError):
        return ""
    if title_id < 6:
        return ""
    return classes.get(key, "badge-title-slate")


@register.filter
def title_tier_badge_class(value):
    """タイトルを下位から上位へ段階的に色分けする（一覧のバッジ表示用）。"""
    classes = {
        "1": "badge-secondary",
        "2": "badge-info",
        "3": "badge-primary",
        "4": "badge-success",
        "5": "badge-title-teal",
        "6": "badge-title-orange",
        "7": "badge-title-purple",
        "8": "badge-title-rose",
        "9": "badge-title-amber",
        "10": "badge-title-fuchsia",
        "11": "badge-title-slate",
    }
    if value in (None, ""):
        return "badge-light text-muted"
    key = str(value).strip()
    return classes.get(key, "badge-light text-muted")


ORDER_STATUS_LABELS = {
    201: "入金待ち",
    202: "入金確認済",
    203: "決済完了",
    204: "出荷依頼済",
    205: "出荷完了",
    206: "キャンセル",
    207: "返品処理中",
    208: "返品処理完了",
    209: "商品交換処理中",
    210: "再出荷依頼中",
    211: "再出荷完了",
}

# 進行状況が一目で分かるよう、待ち＝オレンジ／処理中＝青／完了＝緑／
# 中止・返品＝赤／交換＝紫 で色分けする。
ORDER_STATUS_BADGE_CLASSES = {
    201: "order-status-badge--waiting",
    202: "order-status-badge--progress",
    203: "order-status-badge--progress",
    204: "order-status-badge--progress",
    205: "order-status-badge--done",
    206: "order-status-badge--canceled",
    207: "order-status-badge--canceled",
    208: "order-status-badge--canceled",
    209: "order-status-badge--exchange",
    210: "order-status-badge--progress",
    211: "order-status-badge--done",
}


def _to_order_status(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@register.filter
def order_status_label(value):
    """注文状況コードを日本語ラベルにする。未知のコードはそのまま返す。"""
    status = _to_order_status(value)
    if status is None:
        return value if value not in (None, "") else ""
    return ORDER_STATUS_LABELS.get(status, status)


@register.filter
def order_status_badge_class(value):
    status = _to_order_status(value)
    return ORDER_STATUS_BADGE_CLASSES.get(status, "order-status-badge--unknown")


BV_ACTIVED_FLG_LABELS = {
    0: "未反映",
    1: "反映済",
    3: "反映無効",
}

BV_ACTIVED_FLG_BADGE_CLASSES = {
    0: "order-status-badge--waiting",
    1: "order-status-badge--done",
    3: "order-status-badge--canceled",
}


@register.filter
def bv_actived_flg_label(value):
    """BV反映FLGを日本語ラベルにする。未知の値はそのまま返す。"""
    flag = _to_order_status(value)
    if flag is None:
        return value if value not in (None, "") else ""
    return BV_ACTIVED_FLG_LABELS.get(flag, flag)


@register.filter
def bv_actived_flg_badge_class(value):
    flag = _to_order_status(value)
    return BV_ACTIVED_FLG_BADGE_CLASSES.get(flag, "order-status-badge--unknown")


ORDER_TYPE_LABELS = {
    101: "再購入品",
    102: "初回購入品",
    103: "ランクアップ購入品",
    105: "特別対応購入品",
    200: "クーリングオフ",
}

ORDER_TYPE_BADGE_CLASSES = {
    101: "order-status-badge--progress",
    102: "order-status-badge--done",
    103: "order-status-badge--exchange",
    105: "order-status-badge--waiting",
    200: "order-status-badge--canceled",
}


@register.filter
def order_type_label(value):
    """注文区分コードを日本語ラベルにする。未知のコードはそのまま返す。"""
    order_type = _to_order_status(value)
    if order_type is None:
        return value if value not in (None, "") else ""
    return ORDER_TYPE_LABELS.get(order_type, order_type)


@register.filter
def order_type_badge_class(value):
    order_type = _to_order_status(value)
    return ORDER_TYPE_BADGE_CLASSES.get(order_type, "order-status-badge--unknown")


@register.filter
def is_three_star_title(value):
    if value in (None, ""):
        return False
    try:
        return int(value) >= 6
    except (TypeError, ValueError):
        return False


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
    try:
        if len(text) >= 7 and text[4].upper() == "C":
            year = text[:4]
            month = int(text[5:7])
            return f"{year}年{month}月"

        if len(text) >= 7 and text[4] == "-":
            year = text[:4]
            month = int(text[5:7])
            return f"{year}年{month}月"

        if len(text) >= 6:
            year = text[:4]
            month = int(text[4:6])
            return f"{year}年{month}月"
    except ValueError:
        return text

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


def _resolve_kibetu_choice_mode(request):
    if not request:
        return "recent"
    return request.GET.get("kibetu_choice_mode") or "recent"


def _build_kibetu_period_choices(request, period_type, created_kibetu_set=None, zero_count_kibetu_set=None):
    created_kibetu_set = created_kibetu_set or set()
    zero_count_kibetu_set = zero_count_kibetu_set or set()
    kibetu_choice_mode = _resolve_kibetu_choice_mode(request)

    if period_type == "monthly":
        today = date.today()
        period_choices = (
            MonthlyPeriod.objects.using("rds")
            .filter(Q(year__lt=today.year) | Q(year=today.year, month__lt=today.month))
            .order_by("-kibetu")
        )
        next_completion_kibetu = None
        previous_month = date.today() - relativedelta(months=1)
        previous_month_period = (
            MonthlyPeriod.objects.using("rds")
            .filter(year=previous_month.year, month=previous_month.month)
            .first()
        )
        previous_month_kibetu = (
            previous_month_period.kibetu if previous_month_period else None
        )
    else:
        period_choices = PeriodMaster.objects.using("rds").all()
        today = date.today()
        next_completion_period = (
            period_choices
            .filter(completion_date__gte=today)
            .order_by("completion_date", "-kibetu")
            .first()
        )
        next_completion_kibetu = (
            next_completion_period.kibetu if next_completion_period else None
        )
        previous_month_kibetu = None
        if kibetu_choice_mode != "all":
            recent_start = today - relativedelta(months=5)
            recent_end = today + relativedelta(months=1)
            period_choices = period_choices.filter(
                completion_date__gte=recent_start,
                completion_date__lte=recent_end,
            )
            kibetu_choice_mode = "recent"

        period_choices = period_choices.order_by("-kibetu")

    period_choices = list(period_choices)
    for period in period_choices:
        period.is_zero_count = period.kibetu in zero_count_kibetu_set
        period.is_created = (
            period.kibetu in created_kibetu_set
            and period.kibetu not in zero_count_kibetu_set
        )

    return {
        "period_choices": period_choices,
        "period_type": period_type,
        "kibetu_choice_mode": kibetu_choice_mode,
        "next_completion_kibetu": next_completion_kibetu,
        "previous_month_kibetu": previous_month_kibetu,
    }


@register.inclusion_tag("com/_bonus_calc_kibetu_input.html", takes_context=True)
def bonus_calc_kibetu_input(context, selected_kibetu="", period_type="weekly", required=True):
    request = context.get("request")
    history_target_url_name = str(context.get("history_target_url_name") or "")
    history_target_url_name = history_target_url_name.split(":")[-1]
    history_field = BONUS_HISTORY_FIELD_BY_URL_NAME.get(history_target_url_name)
    created_kibetu_set = set()
    zero_count_kibetu_set = set()
    if history_field:
        for row in context.get("history_rows") or []:
            if row.get(history_field):
                created_kibetu_set.add(row.get("kibetu"))
            if row.get(f"{history_field}_is_empty"):
                zero_count_kibetu_set.add(row.get("kibetu"))

    period_context = _build_kibetu_period_choices(
        request,
        period_type,
        created_kibetu_set=created_kibetu_set,
        zero_count_kibetu_set=zero_count_kibetu_set,
    )
    datalist_id = (
        "bonus-calc-kibetu-monthly"
        if period_type == "monthly"
        else "bonus-calc-kibetu-weekly"
    )

    return {
        "selected_kibetu": selected_kibetu or "",
        "datalist_id": datalist_id,
        "required": required,
        **period_context,
    }


@register.inclusion_tag("com/_business_search_kibetu_input.html", takes_context=True)
def business_search_kibetu_input(
    context,
    q_kibetu="",
    period_type="weekly",
    placeholder="",
    registered_only=False,
    multiple=False,
):
    request = context.get("request")
    created_kibetu_set = set()
    for row in context.get("registration_history_rows") or []:
        kibetu = row.get("kibetu")
        if kibetu and (row.get("row_count") or 0) > 0:
            created_kibetu_set.add(kibetu)

    period_context = _build_kibetu_period_choices(
        request,
        period_type,
        created_kibetu_set=created_kibetu_set,
    )
    if registered_only:
        period_context["period_choices"] = [
            period
            for period in period_context["period_choices"]
            if period.kibetu in created_kibetu_set
        ]

    q_kibetu = q_kibetu or ""
    selected_kibetu_list = parse_kibetu_list(q_kibetu) if multiple else [q_kibetu] if q_kibetu else []

    if multiple:
        default_placeholder = "期別を選択（複数可）"
    else:
        default_placeholder = "期別を入力または選択"

    return {
        "q_kibetu": q_kibetu,
        "selected_kibetu_list": selected_kibetu_list,
        "placeholder": placeholder or default_placeholder,
        "registered_only": registered_only,
        "multiple": multiple,
        **period_context,
    }


@register.inclusion_tag("com/_bonus_calc_period_status.html", takes_context=True)
def bonus_calc_period_status(context, empty_message="期別を指定してください"):
    return {
        "selected_kibetu": (context.get("selected_kibetu") or "").strip(),
        "selected_period": context.get("selected_period"),
        "empty_message": empty_message,
    }


@register.simple_tag(takes_context=True)
def sortable_th(context, column, label, css_class="", width=""):
    request = context.get("request")
    sort = context.get("sort", "")
    direction = context.get("direction", "asc")
    next_direction = context.get("next_direction", "desc")
    extra_class = f" {css_class}" if css_class else ""
    width_attr = format_html(' width="{}"', width) if width else ""

    if not request:
        return format_html(
            '<th class="text-center{}"{}>{}</th>',
            extra_class,
            width_attr,
            label,
        )

    params = request.GET.copy()
    params["sort"] = column
    if sort == column:
        params["direction"] = next_direction
    else:
        params["direction"] = "asc"
    # 並び替え直後は先頭ページから見せる。
    params.pop("page", None)

    indicator = ""
    if sort == column:
        indicator = " ▲" if direction == "asc" else " ▼"

    return format_html(
        '<th class="text-center sortable-th{}"{}>'
        '<a href="?{}" class="sortable-th__link text-dark text-decoration-none">'
        "{}{}</a></th>",
        extra_class,
        width_attr,
        params.urlencode(),
        label,
        indicator,
    )
