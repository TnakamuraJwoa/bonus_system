"""旧システム業績照会。

旧システムから移行した業績テーブル（JP_BR_*_PFM）をそのまま検索・閲覧する画面。
現行の業績検索とは列がまったく違うため、画面ごとに表示列を定義して
1つのテンプレートで描画する。

期別が未指定のときは検索せず、何も表示しない。リセット直後に旧システムの
データが出ないようにするため。
"""

import logging
import math

from django.db import ProgrammingError, connections
from django.views import generic

from connect.business_search_registration import (
    build_kibetu_condition,
    is_missing_table_error,
    join_kibetu_list,
    parse_kibetu_list,
)

from .views import KeysetPaginationMixin


logger = logging.getLogger(__name__)

LEGACY_MEMBER_TABLE = "bonus_db.JP_MM_MEMBER"

PERSON_WEEKLY_TABLE = "bonus_db.JP_BR_PERSON_WEEKLY_PFM"
PERSON_MONTHLY_TABLE = "bonus_db.JP_BR_PERSON_MONTHLY_PFM"
ORG_WEEKLY_TABLE = "bonus_db.JP_BR_ORG_WEEKLY_PFM"
ORG_MONTHLY_TABLE = "bonus_db.JP_BR_ORG_MONTHLY_PFM"


def column(key, label, expression, kind="number"):
    """一覧の1列分の定義。kind は number / text / datetime。"""
    return {
        "key": key,
        "label": label,
        "expression": expression,
        "kind": kind,
    }


COMMON_HEAD_COLUMNS = (
    column("working_stage", "期別", "p.WORKING_STAGE", kind="text"),
    column("member_no", "会員コード", "m.MEMBER_NO", kind="text"),
    column("member_name", "会員名", "m.NAME", kind="text"),
)

UPDATE_TIME_COLUMN = column("update_time", "更新日時", "p.UPDATE_TIME", kind="datetime")

PERSON_COLUMNS = COMMON_HEAD_COLUMNS + (
    column("first_purchase_pv", "初回購入PV", "p.FIRST_PURCHASE_PV"),
    column("first_purchase_bv", "初回購入BV", "p.FIRST_PURCHASE_BV"),
    column("upgrade_pv", "アップグレードPV", "p.UPGRADE_PV"),
    column("upgrade_bv", "アップグレードBV", "p.UPGRADE_BV"),
    column("repeat_purchase_pv", "リピート購入PV", "p.REPEAT_PURCHASE_PV"),
    column("repeat_purchase_bv", "リピート購入BV", "p.REPEAT_PURCHASE_BV"),
    column("newly_increased_pv", "新規増加PV", "p.NEWLY_INCREASED_PV"),
    column("newly_increased_bv", "新規増加BV", "p.NEWLY_INCREASED_BV"),
    column("base_repurchase_bv", "基準リピートBV", "p.BASE_REPURCHASE_BV"),
    UPDATE_TIME_COLUMN,
)

ORG_WEEKLY_COLUMNS = COMMON_HEAD_COLUMNS + (
    column("placement_group_pv", "組織PV", "p.PLACEMENT_GROUP_PV"),
    column("placement_group_bv", "組織BV", "p.PLACEMENT_GROUP_BV"),
    UPDATE_TIME_COLUMN,
)

ORG_MONTHLY_COLUMNS = COMMON_HEAD_COLUMNS + (
    column("placement_group_pv", "組織PV", "p.PLACEMENT_GROUP_PV"),
    column("placement_group_bv", "組織BV", "p.PLACEMENT_GROUP_BV"),
    column("sponsor_group_pv", "スポンサーPV", "p.SPONSOR_GROUP_PV"),
    column("sponsor_group_bv", "スポンサーBV", "p.SPONSOR_GROUP_BV"),
    UPDATE_TIME_COLUMN,
)


class LegacyPerformanceBaseView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "legacy_performance.html"

    result_table = None
    columns = ()
    period_type = "weekly"
    period_label = ""
    target_label = ""
    active_menu = ""
    reset_url_name = ""

    def _build_where(self, q_kibetu_list=(), q_member_no=""):
        where = []
        params = []

        kibetu_sql, kibetu_params = build_kibetu_condition(
            q_kibetu_list,
            column="p.WORKING_STAGE",
        )
        if kibetu_sql:
            where.append(kibetu_sql)
            params.extend(kibetu_params)

        if q_member_no:
            where.append("m.MEMBER_NO LIKE %s")
            params.append(f"{q_member_no}%")

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return where_sql, params

    def _fetch_total_count(self, q_kibetu_list=(), q_member_no=""):
        where_sql, params = self._build_where(
            q_kibetu_list=q_kibetu_list,
            q_member_no=q_member_no,
        )
        sql = f"""
            SELECT COUNT(*)
            FROM {self.result_table} p
            LEFT JOIN {LEGACY_MEMBER_TABLE} m
              ON m.ID = p.MEMBER_ID
            {where_sql}
        """
        with connections["rds"].cursor() as cursor:
            logger.info("旧システム業績件数取得SQLを実行します。table=%s", self.result_table)
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム業績テーブルが未作成です。table=%s", self.result_table)
                    return 0
                raise
        return int(row[0]) if row else 0

    def _fetch_rows(self, q_kibetu_list=(), q_member_no="", limit=200, offset=0):
        where_sql, params = self._build_where(
            q_kibetu_list=q_kibetu_list,
            q_member_no=q_member_no,
        )
        select_sql = ",\n                ".join(
            f'{col["expression"]} AS {col["key"]}' for col in self.columns
        )
        sql = f"""
            SELECT
                {select_sql}
            FROM {self.result_table} p
            LEFT JOIN {LEGACY_MEMBER_TABLE} m
              ON m.ID = p.MEMBER_ID
            {where_sql}
            ORDER BY p.WORKING_STAGE DESC, m.MEMBER_NO
            LIMIT %s OFFSET %s
        """
        with connections["rds"].cursor() as cursor:
            logger.info("旧システム業績一覧取得SQLを実行します。table=%s", self.result_table)
            try:
                cursor.execute(sql, params + [limit, offset])
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム業績テーブルが未作成です。table=%s", self.result_table)
                    return []
                raise
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q_kibetu_list = parse_kibetu_list(self.request.GET.get("q_kibetu"))
        q_kibetu = join_kibetu_list(q_kibetu_list)
        q_member_no = (self.request.GET.get("q_member_no") or "").strip()
        kibetu_choice_mode = self.request.GET.get("kibetu_choice_mode") or "recent"

        per_page = self.get_per_page()

        # 期別を選ぶまでは検索しない。リセット直後も同じ状態にする。
        if q_kibetu_list:
            total_count = self._fetch_total_count(
                q_kibetu_list=q_kibetu_list,
                q_member_no=q_member_no,
            )
        else:
            total_count = 0

        total_pages = max(1, math.ceil(total_count / per_page))
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page

        if q_kibetu_list:
            rows = self._fetch_rows(
                q_kibetu_list=q_kibetu_list,
                q_member_no=q_member_no,
                limit=per_page,
                offset=offset,
            )
        else:
            rows = []

        ctx["q_kibetu"] = q_kibetu
        ctx["q_kibetu_list"] = q_kibetu_list
        ctx["q_member_no"] = q_member_no
        ctx["columns"] = self.columns
        ctx["period_type"] = self.period_type
        ctx["period_label"] = self.period_label
        ctx["target_label"] = self.target_label
        ctx["list_title"] = f"{self.period_label} {self.target_label}一覧"
        ctx["active_menu"] = self.active_menu
        ctx["reset_url_name"] = self.reset_url_name
        ctx["kibetu_required"] = not q_kibetu_list
        base_params = {
            "q_kibetu": q_kibetu,
            "q_member_no": q_member_no,
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


class LegacyPersonalWeekPerformanceView(LegacyPerformanceBaseView):
    result_table = PERSON_WEEKLY_TABLE
    columns = PERSON_COLUMNS
    period_type = "weekly"
    period_label = "週別"
    target_label = "個人業績"
    active_menu = "legacy_personal_week_performance"
    reset_url_name = "connect:legacy_personal_week_performance"


class LegacyTeamWeekPerformanceView(LegacyPerformanceBaseView):
    result_table = ORG_WEEKLY_TABLE
    columns = ORG_WEEKLY_COLUMNS
    period_type = "weekly"
    period_label = "週別"
    target_label = "チーム業績"
    active_menu = "legacy_team_week_performance"
    reset_url_name = "connect:legacy_team_week_performance"


class LegacyPersonalMonthPerformanceView(LegacyPerformanceBaseView):
    result_table = PERSON_MONTHLY_TABLE
    columns = PERSON_COLUMNS
    period_type = "monthly"
    period_label = "月別"
    target_label = "個人業績"
    active_menu = "legacy_personal_month_performance"
    reset_url_name = "connect:legacy_personal_month_performance"


class LegacyTeamMonthPerformanceView(LegacyPerformanceBaseView):
    result_table = ORG_MONTHLY_TABLE
    columns = ORG_MONTHLY_COLUMNS
    period_type = "monthly"
    period_label = "月別"
    target_label = "チーム業績"
    active_menu = "legacy_team_month_performance"
    reset_url_name = "connect:legacy_team_month_performance"
