import logging
import math
from urllib.parse import quote

from django.contrib import messages
from django.db import ProgrammingError, connections, transaction
from django.shortcuts import redirect
from django.views import generic

from connect.business_search_registration import fetch_registration_history_rows
from connect.sql.register_sql import (
    get_month_team_performance_insert_data,
    get_week_team_performance_insert_data,
)
from connect.sql.team_performance_detail_sql import (
    MONTH_TEAM_PERFORMANCE_DETAIL_SQL,
    WEEK_TEAM_PERFORMANCE_DETAIL_SQL,
)

from .models import MonthlyPeriod, PeriodMaster
from .views import (
    KeysetPaginationMixin,
    auto_register_purchase_info_for_kibetu_month,
)


logger = logging.getLogger(__name__)

TEAM_BUSINESS_SEARCH_RESULT_TABLE = "bonus_db.B_team_business_search_result"


def is_missing_table_error(exc):
    return bool(exc.args and exc.args[0] == 1146)


def has_team_performance_detail(detail_table, kibetu, period_type):
    if not kibetu:
        return False

    sql = f"""
        SELECT 1
        FROM {detail_table}
        WHERE kibetu = %s
          AND period_type = %s
        LIMIT 1
    """
    with connections["rds"].cursor() as cursor:
        logger.info(
            "チーム業績登録有無確認SQLを実行します。table=%s kibetu=%s period_type=%s",
            detail_table,
            kibetu,
            period_type,
        )
        try:
            cursor.execute(sql, [kibetu, period_type])
            return cursor.fetchone() is not None
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("チーム業績明細テーブルが未作成です。table=%s", detail_table)
                return False
            raise


def has_purchase_info_for_bonus_payment_date_range(st_date, end_date):
    with connections["rds"].cursor() as cursor:
        logger.info(
            "購入情報存在確認SQLを実行します。st_date=%s end_date=%s",
            st_date,
            end_date,
        )
        cursor.execute(
            """
                SELECT 1
                FROM bonus_db.purchase_info_list
                WHERE bonus_payment_date >= %s
                  AND bonus_payment_date <= %s
                LIMIT 1
            """,
            [st_date, end_date],
        )
        return cursor.fetchone() is not None


def resolve_week_team_performance_params(kibetu):
    period = PeriodMaster.objects.using("rds").filter(kibetu=kibetu).first()
    if not period or not period.st_date or not period.end_date:
        raise ValueError("選択された期別が存在しないか、開始日・終了日が未設定です。")
    return period.st_date, period.end_date


def resolve_month_team_performance_params(kibetu):
    period = MonthlyPeriod.objects.using("rds").filter(kibetu=kibetu).first()
    if not period:
        raise ValueError("選択された期別が存在しません。")
    return period.year, period.month


def ensure_team_performance_purchase_info(request, kibetu, period_type):
    try:
        if period_type == "weekly":
            st_date, end_date = resolve_week_team_performance_params(kibetu)
        else:
            register_year, register_month = resolve_month_team_performance_params(kibetu)
    except ValueError as exc:
        messages.error(request, str(exc))
        return False

    if period_type == "weekly":
        if has_purchase_info_for_bonus_payment_date_range(st_date, end_date):
            return True

        messages.error(
            request,
            (
                "指定期間の購入情報がないため登録できません: "
                f"{st_date} ～ {end_date}"
            ),
        )
        return False

    return auto_register_purchase_info_for_kibetu_month(
        request,
        register_year,
        register_month,
    )


def fetch_team_performance_detail_rows(
    detail_table,
    period_type,
    q_kibetu="",
    q_upper_code="",
    q_purchaser_code="",
    limit=200,
    offset=0,
):
    where = ["period_type = %s"]
    params = [period_type]

    if q_kibetu:
        where.append("kibetu = %s")
        params.append(q_kibetu)

    if q_upper_code:
        where.append("upper_code LIKE %s")
        params.append(f"%{q_upper_code}%")

    if q_purchaser_code:
        where.append("purchaser_code LIKE %s")
        params.append(f"%{q_purchaser_code}%")

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT
            id,
            kibetu,
            upper_code,
            line_code,
            purchaser_code,
            purchaser_name,
            lvl,
            sum_bv,
            created_at,
            updated_at
        FROM {detail_table}
        {where_sql}
        ORDER BY kibetu DESC, upper_code, line_code, purchaser_code, lvl
        LIMIT %s OFFSET %s
    """
    with connections["rds"].cursor() as cursor:
        logger.info("チーム業績明細一覧取得SQLを実行します。table=%s", detail_table)
        try:
            cursor.execute(sql, params + [limit, offset])
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("チーム業績明細テーブルが未作成です。table=%s", detail_table)
                return []
            raise


def count_team_performance_detail_rows(
    detail_table,
    period_type,
    q_kibetu="",
    q_upper_code="",
    q_purchaser_code="",
):
    where = ["period_type = %s"]
    params = [period_type]

    if q_kibetu:
        where.append("kibetu = %s")
        params.append(q_kibetu)

    if q_upper_code:
        where.append("upper_code LIKE %s")
        params.append(f"%{q_upper_code}%")

    if q_purchaser_code:
        where.append("purchaser_code LIKE %s")
        params.append(f"%{q_purchaser_code}%")

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT COUNT(*)
        FROM {detail_table}
        {where_sql}
    """
    with connections["rds"].cursor() as cursor:
        logger.info("チーム業績明細件数取得SQLを実行します。table=%s", detail_table)
        try:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        except ProgrammingError as exc:
            if is_missing_table_error(exc):
                logger.info("チーム業績明細テーブルが未作成です。table=%s", detail_table)
                return 0
            raise
    return int(row[0]) if row else 0


def calculate_team_performance_detail_rows(period_type, kibetu):
    if period_type == "weekly":
        st_date, end_date = resolve_week_team_performance_params(kibetu)
        sql = WEEK_TEAM_PERFORMANCE_DETAIL_SQL
        params = [st_date, end_date]
        logger.info(
            "チーム業績明細計算SQLを実行します。period_type=weekly st_date=%s end_date=%s",
            st_date,
            end_date,
        )
    else:
        register_year, register_month = resolve_month_team_performance_params(kibetu)
        sql = MONTH_TEAM_PERFORMANCE_DETAIL_SQL
        params = [register_year, register_month]
        logger.info(
            "チーム業績明細計算SQLを実行します。period_type=monthly register_year=%s register_month=%s",
            register_year,
            register_month,
        )

    with connections["rds"].cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def filter_team_performance_preview_rows(rows, q_kibetu, q_upper_code="", q_purchaser_code=""):
    filtered_rows = []
    q_upper_code = q_upper_code.lower()
    q_purchaser_code = q_purchaser_code.lower()

    for row in rows:
        upper_code = str(row.get("upper_code") or "")
        purchaser_code = str(row.get("purchaser_code") or "")
        if q_upper_code and q_upper_code not in upper_code.lower():
            continue
        if q_purchaser_code and q_purchaser_code not in purchaser_code.lower():
            continue

        preview_row = row.copy()
        preview_row["kibetu"] = q_kibetu
        filtered_rows.append(preview_row)

    return filtered_rows


def register_team_performance_detail(request, detail_table, kibetu, insert_data_fn, period_type):
    if not ensure_team_performance_purchase_info(request, kibetu, period_type):
        return False, 0

    try:
        rows = calculate_team_performance_detail_rows(period_type, kibetu)
    except ValueError as exc:
        messages.error(request, str(exc))
        return False, 0

    if not rows:
        messages.warning(request, "登録対象データがありません。")
        return False, 0

    insert_sql, insert_params = insert_data_fn(kibetu, rows)
    delete_sql = f"DELETE FROM {detail_table} WHERE kibetu = %s AND period_type = %s"

    try:
        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                logger.info(
                    "チーム業績明細削除SQLを実行します。table=%s kibetu=%s period_type=%s",
                    detail_table,
                    kibetu,
                    period_type,
                )
                cursor.execute(delete_sql, [kibetu, period_type])
                logger.info(
                    "チーム業績明細登録SQLを実行します。table=%s kibetu=%s period_type=%s count=%s",
                    detail_table,
                    kibetu,
                    period_type,
                    len(insert_params),
                )
                cursor.executemany(insert_sql, insert_params)
    except ProgrammingError as exc:
        if is_missing_table_error(exc):
            messages.error(request, "チーム業績明細テーブルが未作成のため登録できません。")
            return False, 0
        raise

    return True, len(insert_params)


class BusinessTeamPerformanceDetailMixin(KeysetPaginationMixin):
    detail_table = None
    insert_data_fn = None
    redirect_url_name = None
    reset_url_name = None
    active_menu = None
    period_label = None
    period_type = None
    team_help_key = None
    template_name = None
    registration_history_modal_id = ""
    registration_modal_title = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q_kibetu = (self.request.GET.get("q_kibetu") or "").strip()
        q_upper_code = (self.request.GET.get("q_upper_code") or "").strip()
        q_purchaser_code = (self.request.GET.get("q_purchaser_code") or "").strip()
        kibetu_choice_mode = self.request.GET.get("kibetu_choice_mode") or "recent"

        per_page = self.get_per_page()
        is_registered = has_team_performance_detail(
            self.detail_table,
            q_kibetu,
            self.period_type,
        )
        is_preview = False
        preview_error = ""

        if q_kibetu and not is_registered:
            try:
                preview_rows = calculate_team_performance_detail_rows(
                    self.period_type,
                    q_kibetu,
                )
            except ValueError as exc:
                preview_rows = []
                preview_error = str(exc)

            preview_rows = filter_team_performance_preview_rows(
                preview_rows,
                q_kibetu,
                q_upper_code=q_upper_code,
                q_purchaser_code=q_purchaser_code,
            )
            total_count = len(preview_rows)
            total_pages = max(1, math.ceil(total_count / per_page))
            page = self.get_page_number(total_pages)
            offset = (page - 1) * per_page
            rows = preview_rows[offset : offset + per_page]
            is_preview = True
        else:
            total_count = count_team_performance_detail_rows(
                self.detail_table,
                self.period_type,
                q_kibetu=q_kibetu,
                q_upper_code=q_upper_code,
                q_purchaser_code=q_purchaser_code,
            )
            total_pages = max(1, math.ceil(total_count / per_page))
            page = self.get_page_number(total_pages)
            offset = (page - 1) * per_page

            rows = fetch_team_performance_detail_rows(
                self.detail_table,
                self.period_type,
                q_kibetu=q_kibetu,
                q_upper_code=q_upper_code,
                q_purchaser_code=q_purchaser_code,
                limit=per_page,
                offset=offset,
            )

        ctx["q_kibetu"] = q_kibetu
        ctx["q_upper_code"] = q_upper_code
        ctx["q_purchaser_code"] = q_purchaser_code
        ctx["period_label"] = self.period_label
        ctx["period_type"] = self.period_type
        ctx["active_menu"] = self.active_menu
        ctx["reset_url_name"] = self.reset_url_name
        ctx["team_help_key"] = self.team_help_key
        ctx["is_team_performance_registered"] = is_registered
        ctx["is_team_performance_preview"] = is_preview
        ctx["team_performance_preview_error"] = preview_error
        ctx["registration_history_rows"] = fetch_registration_history_rows(
            self.detail_table,
            period_type=self.period_type,
        )
        ctx["registration_history_modal_id"] = self.registration_history_modal_id
        ctx["registration_modal_title"] = self.registration_modal_title
        ctx["registration_target_url_name"] = self.redirect_url_name
        base_params = {
            "q_kibetu": q_kibetu,
            "q_upper_code": q_upper_code,
            "q_purchaser_code": q_purchaser_code,
            "per_page": per_page,
        }
        if self.period_type == "weekly":
            base_params["kibetu_choice_mode"] = kibetu_choice_mode
        return self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params=base_params,
        )

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        q_kibetu = (request.POST.get("kibetu") or "").strip()

        if action != "register_team_performance":
            messages.error(request, "不正な操作です。")
            return redirect(self.redirect_url_name)

        if not q_kibetu:
            messages.error(request, "期別を選択してください。")
            return redirect(self.redirect_url_name)

        is_registered = has_team_performance_detail(
            self.detail_table,
            q_kibetu,
            self.period_type,
        )
        confirm_label = "再登録" if is_registered else "登録"

        success, count = register_team_performance_detail(
            request,
            self.detail_table,
            q_kibetu,
            type(self).insert_data_fn,
            self.period_type,
        )
        if success:
            detail_label = (
                "週別チーム業績明細"
                if self.period_label == "週別"
                else "月別チーム業績明細"
            )
            messages.success(
                request,
                f"{count}件を{detail_label}に{confirm_label}しました。",
            )
            return redirect(
                f"{reverse_url(self.redirect_url_name)}?q_kibetu={quote(q_kibetu)}"
            )

        return redirect(
            f"{reverse_url(self.redirect_url_name)}?q_kibetu={quote(q_kibetu)}"
        )


def reverse_url(url_name):
    from django.urls import reverse

    return reverse(url_name)


class BusinessTeamWeekPerformanceView(BusinessTeamPerformanceDetailMixin, generic.TemplateView):
    template_name = "business_team_performance_detail.html"
    detail_table = TEAM_BUSINESS_SEARCH_RESULT_TABLE
    insert_data_fn = get_week_team_performance_insert_data
    redirect_url_name = "connect:business_team_week_performance"
    reset_url_name = "connect:business_team_week_performance"
    active_menu = "business_team_week_performance"
    period_label = "週別"
    period_type = "weekly"
    team_help_key = "business_team_week_performance"
    registration_history_modal_id = "weekTeamRegistrationModal"
    registration_modal_title = "登録履歴（週別 チーム業績）"


class BusinessTeamMonthPerformanceView(BusinessTeamPerformanceDetailMixin, generic.TemplateView):
    template_name = "business_team_performance_detail.html"
    detail_table = TEAM_BUSINESS_SEARCH_RESULT_TABLE
    insert_data_fn = get_month_team_performance_insert_data
    redirect_url_name = "connect:business_team_performance"
    reset_url_name = "connect:business_team_performance"
    active_menu = "business_team_performance"
    period_label = "月別"
    period_type = "monthly"
    team_help_key = "business_team_performance"
    registration_history_modal_id = "monthTeamRegistrationModal"
    registration_modal_title = "登録履歴（月別 チーム業績）"
