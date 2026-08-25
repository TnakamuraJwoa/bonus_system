"""旧BONUS_SYSTEM（リンパ）の注文一覧。

現行の NEXUS 注文一覧と同じ検索・一覧・Excel・詳細の形で、
bonus_db.JP_OM_ORDERS をそのまま表示する。
"""

import hashlib
import json
import logging
import math
from datetime import date, datetime
from urllib.parse import urlencode

import openpyxl
from django.contrib import messages
from django.core.cache import cache
from django.db import ProgrammingError, connections
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import generic

from connect.business_search_registration import is_missing_table_error
from connect.order_field_labels import get_legacy_order_field_label
from connect.templatetags.custom_filters import jst_datetime
from connect.views import (
    KeysetPaginationMixin,
    add_sort_params,
    get_bonus_sort_context,
)


logger = logging.getLogger(__name__)

LEGACY_ORDERS_TABLE = "bonus_db.JP_OM_ORDERS"
LEGACY_MEMBER_TABLE = "bonus_db.JP_MM_MEMBER"

# 注文が持つ MEMBER_ID は会員テーブルの内部 ID なので、
# 画面に出す会員コードは JP_MM_MEMBER.MEMBER_NO を引いて表示する。
MEMBER_JOIN_SQL = f"""
            LEFT JOIN {LEGACY_MEMBER_TABLE} m
              ON m.ID = o.MEMBER_ID
"""

# 旧システムにはコードマスタが無いため、現行 orders との突き合わせと
# 入金日・取消日の有無から意味を割り出したもの。
# 注文区分は DOC_NO の枝番を落として現行 orders と結合した226,805件で
# 10=初回購入品 / 20=ランクアップ購入品 / 30=再購入品 が完全に一致した。
# 注文状況は入金取消日・BV取消日が必ず入る -110 が取消、それ以外が有効。
# 件数の少ない 30/50/55/60 は根拠が無いのでコードのまま見せる。
ORDER_TYPE_LABELS = {
    "10": "初回購入品",
    "20": "ランクアップ購入品",
    "30": "再購入品",
}
ORDER_STATUS_LABELS = {
    "20": "有効",
    "35": "未処理",
    "30": "その他(30)",
    "50": "その他(50)",
    "55": "その他(55)",
    "60": "その他(60)",
    "-100": "無効",
    "-110": "取消",
}
ORDER_STATUS_BADGE_CLASSES = {
    "20": "order-status-badge--done",
    "35": "order-status-badge--waiting",
    "-100": "order-status-badge--canceled",
    "-110": "order-status-badge--canceled",
}

ORDER_TYPE_CHOICES = tuple(ORDER_TYPE_LABELS.items())
ORDER_STATUS_CHOICES = tuple(ORDER_STATUS_LABELS.items())


def order_type_label(value):
    """注文区分コードを日本語にする。未知のコードはそのまま返す。"""
    if value in (None, ""):
        return ""
    key = str(value).strip()
    return ORDER_TYPE_LABELS.get(key, key)


def order_status_label(value):
    """注文状況コードを日本語にする。未知のコードはそのまま返す。"""
    if value in (None, ""):
        return ""
    key = str(value).strip()
    return ORDER_STATUS_LABELS.get(key, key)


def order_status_badge_class(value):
    """旧注文状況コードに対応するバッジ色を返す。"""
    if value in (None, ""):
        return "order-status-badge--unknown"
    key = str(value).strip()
    return ORDER_STATUS_BADGE_CLASSES.get(key, "order-status-badge--unknown")


MIN_ORDER_YEAR = 1900
MAX_ORDER_YEAR = 2999


def _parse_int(value):
    """数値以外は None にする。自由入力の年・月に文字が入っても検索を壊さないため。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def order_date_range(year, month):
    """注文年・注文月から ORDER_DATE の範囲を返す。年が無いときは範囲を作れないので None。"""
    if year is None or not MIN_ORDER_YEAR <= year <= MAX_ORDER_YEAR:
        return None

    if month is None:
        return date(year, 1, 1), date(year + 1, 1, 1)

    start = date(year, month, 1)
    if month == 12:
        return start, date(year + 1, 1, 1)
    return start, date(year, month + 1, 1)


class LegacyOrdersView(KeysetPaginationMixin, generic.TemplateView):
    template_name = "legacy_orders.html"

    TOTAL_COUNT_CACHE_TIMEOUT = 600

    SORT_COLUMNS = {
        # id は列として出していないが、既定の並び順（採番順＝新しい順）に使う。
        "id": "o.ID",
        "order_code": "o.DOC_NO",
        "order_status": "o.ORDER_STATUS",
        "order_type": "o.ORDER_TYPE",
        "order_year": "YEAR(o.ORDER_DATE)",
        "order_month": "MONTH(o.ORDER_DATE)",
        "member_no": "m.MEMBER_NO",
        "order_name": "o.FIRSTNAME",
        "total_price": "o.TOTAL_NET_AMOUNT",
        "total_bv": "o.TOTAL_BV",
        "order_at": "o.ORDER_DATE",
        "created_at": "o.CREATE_DATE",
    }

    def _get_sort_context(self):
        return get_bonus_sort_context(
            self.request,
            self.SORT_COLUMNS,
            default_sort="id",
            default_direction="desc",
        )

    def _build_where(
        self,
        q_order_code="",
        q_member_id="",
        q_name="",
        q_order_statuses=None,
        q_order_types=None,
        q_order_from="",
        q_order_to="",
        q_year="",
        q_month="",
    ):
        if q_order_statuses is None:
            q_order_statuses = []
        if q_order_types is None:
            q_order_types = []

        where = []
        params = []

        if q_order_code:
            where.append("o.DOC_NO LIKE %s")
            params.append(f"%{q_order_code}%")

        if q_member_id:
            where.append("m.MEMBER_NO LIKE %s")
            params.append(f"%{q_member_id}%")

        if q_name:
            where.append("(o.FIRSTNAME LIKE %s OR o.LASTNAME LIKE %s)")
            params.append(f"%{q_name}%")
            params.append(f"%{q_name}%")

        if q_order_statuses:
            placeholders = ", ".join(["%s"] * len(q_order_statuses))
            where.append(f"o.ORDER_STATUS IN ({placeholders})")
            params.extend(q_order_statuses)

        if q_order_types:
            placeholders = ", ".join(["%s"] * len(q_order_types))
            where.append(f"o.ORDER_TYPE IN ({placeholders})")
            params.extend(q_order_types)

        if q_order_from:
            where.append("o.ORDER_DATE >= %s")
            params.append(q_order_from)

        if q_order_to:
            where.append("o.ORDER_DATE < DATE_ADD(%s, INTERVAL 1 DAY)")
            params.append(q_order_to)

        year = _parse_int(q_year)
        month = _parse_int(q_month)
        if month is not None and not 1 <= month <= 12:
            month = None

        date_range = order_date_range(year, month)
        if date_range:
            where.append("o.ORDER_DATE >= %s AND o.ORDER_DATE < %s")
            params.extend(date_range)
        elif month is not None:
            where.append("MONTH(o.ORDER_DATE) = %s")
            params.append(month)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return where_sql, params

    def _total_count_cache_key(self, **filters):
        signature = json.dumps(filters, sort_keys=True, default=str)
        digest = hashlib.md5(signature.encode("utf-8")).hexdigest()
        return f"legacy_orders:total_count:{digest}"

    def _fetch_total_count(self, **filters):
        """一覧の総件数を返す。

        JP_OM_ORDERS は 87 万件・177MB でインデックスが無いため、COUNT(*) だけで
        6 秒前後かかる。旧システムからの移行コピーで再取込のときしか中身が
        変わらないので、条件ごとに現行 orders より長めにキャッシュする。
        """
        cache_key = self._total_count_cache_key(**filters)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        where_sql, params = self._build_where(**filters)
        # 件数だけなら会員名は要らないので、会員コードで絞るときにだけ JOIN する。
        # 87万件に対する無駄な結合を避けるため。
        join_sql = MEMBER_JOIN_SQL if filters.get("q_member_id") else ""
        sql = f"""
            SELECT COUNT(*)
            FROM {LEGACY_ORDERS_TABLE} o
            {join_sql}
            {where_sql}
        """
        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム注文テーブルが未作成です。table=%s", LEGACY_ORDERS_TABLE)
                    return 0
                raise

        total_count = int(row[0]) if row else 0
        cache.set(cache_key, total_count, self.TOTAL_COUNT_CACHE_TIMEOUT)
        return total_count

    def _fetch_rows(self, limit=200, offset=0, order_sql="", **filters):
        where_sql, params = self._build_where(**filters)
        sql = f"""
            SELECT
                o.ID AS id,
                o.DOC_NO AS order_code,
                o.ORDER_STATUS AS order_status,
                o.ORDER_TYPE AS order_type,
                YEAR(o.ORDER_DATE) AS order_year,
                MONTH(o.ORDER_DATE) AS order_month,
                m.MEMBER_NO AS member_no,
                o.FIRSTNAME AS order_name,
                o.TOTAL_NET_AMOUNT AS total_price,
                o.TOTAL_BV AS total_bv,
                o.ORDER_DATE AS order_at,
                o.CREATE_DATE AS created_at
            FROM {LEGACY_ORDERS_TABLE} o
            {MEMBER_JOIN_SQL}
            {where_sql}
            ORDER BY {order_sql or "o.ID DESC"}, o.ID DESC
            LIMIT %s OFFSET %s
        """
        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(sql, params + [limit, offset])
                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム注文テーブルが未作成です。table=%s", LEGACY_ORDERS_TABLE)
                    return []
                raise

        for row in rows:
            if row.get("id") is not None:
                row["id"] = int(row["id"])
            row["order_status_label"] = order_status_label(row.get("order_status"))
            row["order_status_badge_class"] = order_status_badge_class(
                row.get("order_status")
            )
            row["order_type_label"] = order_type_label(row.get("order_type"))
        return rows

    def _get_filters(self):
        q_order_statuses = [
            x for x in self.request.GET.getlist("q_order_status") if x
        ]
        q_order_types = [
            x for x in self.request.GET.getlist("q_order_type") if x
        ]
        return {
            "q_order_code": (self.request.GET.get("q_order_code") or "").strip(),
            "q_member_id": (self.request.GET.get("q_member_id") or "").strip(),
            "q_name": (self.request.GET.get("q_name") or "").strip(),
            "q_order_statuses": q_order_statuses,
            "q_order_types": q_order_types,
            "q_order_from": (self.request.GET.get("q_order_from") or "").strip(),
            "q_order_to": (self.request.GET.get("q_order_to") or "").strip(),
            "q_year": (self.request.GET.get("q_year") or "").strip(),
            "q_month": (self.request.GET.get("q_month") or "").strip(),
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = self._get_filters()
        q_order_statuses = filters["q_order_statuses"]
        q_order_types = filters["q_order_types"]
        per_page = self.get_per_page()
        sort_ctx = self._get_sort_context()
        ctx.update(sort_ctx)

        total_count = self._fetch_total_count(**filters)
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count else 1
        page = self.get_page_number(total_pages)
        offset = (page - 1) * per_page
        rows = (
            self._fetch_rows(
                limit=per_page,
                offset=offset,
                order_sql=sort_ctx["order_sql"],
                **filters,
            )
            if total_count
            else []
        )

        ctx["q_order_code"] = filters["q_order_code"]
        ctx["q_member_id"] = filters["q_member_id"]
        ctx["q_name"] = filters["q_name"]
        ctx["q_order_statuses"] = q_order_statuses
        ctx["q_order_types"] = q_order_types
        ctx["q_order_from"] = filters["q_order_from"]
        ctx["q_order_to"] = filters["q_order_to"]
        ctx["q_year"] = filters["q_year"]
        ctx["q_month"] = filters["q_month"]
        ctx["order_type_choices"] = ORDER_TYPE_CHOICES
        ctx["order_status_choices"] = ORDER_STATUS_CHOICES
        ctx["active_menu"] = "legacy_orders"
        ctx["list_title"] = "旧BONUS_SYSTEM(リンパ) 注文一覧"

        base_params = {}
        for key in (
            "q_order_code",
            "q_member_id",
            "q_name",
            "q_order_from",
            "q_order_to",
            "q_year",
            "q_month",
        ):
            value = filters[key]
            if value:
                base_params[key] = value
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        add_sort_params(base_params, sort_ctx)

        ctx = self.set_page_context(
            ctx=ctx,
            rows=rows,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            base_params=base_params,
        )

        base_qs = ctx["base_qs"]
        for status in q_order_statuses:
            if base_qs:
                base_qs += "&"
            base_qs += urlencode({"q_order_status": status})
        for order_type in q_order_types:
            if base_qs:
                base_qs += "&"
            base_qs += urlencode({"q_order_type": order_type})
        ctx["base_qs"] = base_qs
        return ctx


class LegacyOrdersExportView(LegacyOrdersView):
    """絞り込み条件そのままで Excel 出力する。

    旧テーブルはインデックスが無く 1 回の取得ごとに全件走査になるため、
    チャンクを上限と同じにして走査を 1 回で済ませている。
    """

    EXPORT_FETCH_SIZE = 10000
    MAX_EXPORT_ROWS = 10000

    EXPORT_HEADER = [
        "注文番号",
        "注文状況",
        "注文区分",
        "注文年",
        "注文月",
        "会員ID",
        "注文者_氏名",
        "購入合計金額",
        "合計BV",
        "注文日",
        "作成日時",
    ]

    def _fetch_export_rows(self, last_id=None, limit=None, **filters):
        where_sql, params = self._build_where(**filters)
        if last_id is not None:
            keyset_sql = "o.ID < %s"
            if where_sql:
                where_sql = where_sql + " AND " + keyset_sql
            else:
                where_sql = "WHERE " + keyset_sql
            params = params + [last_id]

        sql = f"""
            SELECT
                o.ID,
                o.DOC_NO,
                o.ORDER_STATUS,
                o.ORDER_TYPE,
                YEAR(o.ORDER_DATE),
                MONTH(o.ORDER_DATE),
                m.MEMBER_NO,
                o.FIRSTNAME,
                o.TOTAL_NET_AMOUNT,
                o.TOTAL_BV,
                o.ORDER_DATE,
                o.CREATE_DATE
            FROM {LEGACY_ORDERS_TABLE} o
            {MEMBER_JOIN_SQL}
            {where_sql}
            ORDER BY o.ID DESC
            LIMIT %s
        """
        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(sql, params + [limit or self.EXPORT_FETCH_SIZE])
                return cursor.fetchall()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム注文テーブルが未作成です。table=%s", LEGACY_ORDERS_TABLE)
                    return []
                raise

    @staticmethod
    def _excel_value(value):
        if isinstance(value, datetime):
            return jst_datetime(value).replace(tzinfo=None)
        return value

    def _row_to_excel(self, row):
        # ID はキーセット用なので Excel には出さない
        values = [self._excel_value(value) for value in row[1:]]
        # 並びは EXPORT_HEADER と同じ（注文番号, 注文状況, 注文区分, ...）
        values[1] = order_status_label(values[1])
        values[2] = order_type_label(values[2])
        return values

    def get(self, request, *args, **kwargs):
        filters = self._get_filters()
        total_count = self._fetch_total_count(**filters)

        if total_count == 0:
            messages.error(request, "出力対象のデータがありません。")
            return redirect(self._back_url(request))

        if total_count > self.MAX_EXPORT_ROWS:
            messages.error(
                request,
                f"対象が{total_count:,}件あります。"
                f"Excel出力は{self.MAX_EXPORT_ROWS:,}件までです。"
                "検索条件を絞り込んでください。",
            )
            return redirect(self._back_url(request))

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet("旧システム注文一覧")
        ws.append(self.EXPORT_HEADER)

        last_id = None
        while True:
            rows = self._fetch_export_rows(
                last_id=last_id,
                limit=self.EXPORT_FETCH_SIZE,
                **filters,
            )
            if not rows:
                break
            for row in rows:
                ws.append(self._row_to_excel(row))
            last_id = rows[-1][0]
            if len(rows) < self.EXPORT_FETCH_SIZE:
                break

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="legacy_orders.xlsx"'
        wb.save(response)
        return response

    @staticmethod
    def _back_url(request):
        query = request.GET.urlencode()
        url = reverse("connect:legacy_orders")
        return f"{url}?{query}" if query else url


class LegacyOrderDetailView(generic.TemplateView):
    template_name = "legacy_order_detail.html"

    @staticmethod
    def _format_order_value(value):
        if value is None:
            return ""
        if isinstance(value, datetime):
            return jst_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
        return value

    def _detail_value(self, col, value):
        if col == "ORDER_STATUS":
            return order_status_label(value)
        if col == "ORDER_TYPE":
            return order_type_label(value)
        return self._format_order_value(value)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order_id = self.kwargs.get("pk")
        sql = f"""
            SELECT *
            FROM {LEGACY_ORDERS_TABLE}
            WHERE ID = %s
            LIMIT 1
        """
        row = None
        cols = []
        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(sql, [order_id])
                cols = [c[0] for c in cursor.description] if cursor.description else []
                row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム注文テーブルが未作成です。table=%s", LEGACY_ORDERS_TABLE)
                else:
                    raise

        ctx["active_menu"] = "legacy_orders"
        if row:
            order = dict(zip(cols, row))
            ctx["order"] = order
            ctx["order_rows"] = [
                (
                    col,
                    get_legacy_order_field_label(col),
                    self._detail_value(col, order.get(col)),
                )
                for col in cols
            ]
        else:
            ctx["order"] = None
            ctx["order_rows"] = []
        return ctx
