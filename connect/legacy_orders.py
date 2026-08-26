"""旧BONUS_SYSTEM（リンパ）の注文一覧。

現行の NEXUS 注文一覧と同じ検索・一覧・Excel・詳細の形で、
bonus_db.JP_OM_ORDERS をそのまま表示する。
"""

import hashlib
import json
import logging
import math
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import openpyxl
from accounts.access import get_user_access
from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.core.cache import cache
from django.db import ProgrammingError, connections, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import generic

from connect.audit import fetch_one_dict, record_change_audit
from connect.business_search_registration import is_missing_table_error
from connect.order_field_labels import get_legacy_order_field_label
from connect.templatetags.custom_filters import as_db_datetime, db_datetime
from connect.views import (
    KeysetPaginationMixin,
    add_sort_params,
    format_target_month,
    get_bonus_sort_context,
    parse_target_month,
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

# 会員コードの部分一致を IN 句に展開する上限。これを超える会員が該当したときは
# 従来どおり会員テーブルと結合して絞る。
MEMBER_MATCH_LIMIT = 10000

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


def parse_order_month(value):
    """注文年月（YYYY-MM）を年・月に分ける。選択なしや不正な値は (None, None)。"""
    try:
        return parse_target_month(value)
    except (AttributeError, TypeError, ValueError):
        return None, None


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
    TOTAL_COUNT_CACHE_VERSION_KEY = "legacy_orders:total_count_version"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # 一覧・件数・Excel出力で同じ会員の引き当てを使い回すリクエスト内キャッシュ
        self._member_id_cache = {}

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
        "bonus_date": "o.BONUS_DATE",
        "created_at": "o.CREATE_DATE",
    }

    def _get_sort_context(self):
        return get_bonus_sort_context(
            self.request,
            self.SORT_COLUMNS,
            default_sort="id",
            default_direction="desc",
        )

    def _get_month_choices(self):
        """注文年月プルダウンの選択肢を新しい順で返す。

        年月を DISTINCT で数え上げると注文日索引を 43 万件ぶん読むことになり
        10 秒を超えるので、最初と最後の注文日だけを引いてその間の年月を並べる。
        どちらも索引の端を見るだけなので 10ms 未満で返る。

        ORDER_DATE には 2201 年のような明らかな誤りが混ざっているため、
        最新は来月までに収まるもののうち一番新しい注文日から取り、
        最古もそこから 20 年前までで打ち切る。
        """
        # 上限を付けた降順 LIMIT 1 なら、索引をその位置から逆に 1 件読むだけで済む。
        # MAX(ORDER_DATE) に WHERE を付けると範囲走査に落ちて 9 秒かかる。
        newest_sql = f"""
            SELECT o.ORDER_DATE
            FROM {LEGACY_ORDERS_TABLE} o
            WHERE o.ORDER_DATE < %s
            ORDER BY o.ORDER_DATE DESC
            LIMIT 1
        """
        oldest_sql = f"SELECT MIN(o.ORDER_DATE) FROM {LEGACY_ORDERS_TABLE} o"

        today = date.today()
        upper_bound = date(today.year, today.month, 1) + relativedelta(months=2)

        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(newest_sql, [upper_bound])
                newest_row = cursor.fetchone()
                cursor.execute(oldest_sql)
                oldest_row = cursor.fetchone()
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info(
                        "旧システム注文テーブルが未作成です。table=%s",
                        LEGACY_ORDERS_TABLE,
                    )
                    return []
                raise

        newest_date = newest_row[0] if newest_row else None
        oldest_date = oldest_row[0] if oldest_row else None
        if not newest_date or not oldest_date:
            return []

        newest = (newest_date.year, newest_date.month)
        oldest = max(
            (oldest_date.year, oldest_date.month),
            (newest[0] - 20, newest[1]),
        )

        choices = []
        year, month = newest
        while (year, month) >= oldest:
            choices.append(
                {
                    "value": format_target_month(year, month),
                    "year": year,
                    "month": month,
                }
            )
            if month == 1:
                year, month = year - 1, 12
            else:
                month -= 1
        return choices

    def _build_order_by(self, sort_ctx):
        """並び替え句を組み立てる。

        同順位を決める ID は並び替え列と同じ向きに揃える。向きが混ざると MySQL は
        二次インデックス（末尾に主キーを含む）を並び替えに使えず、全走査 +
        filesort に落ちる。
        """
        column = self.SORT_COLUMNS.get(sort_ctx["sort"], "o.ID")
        direction = "DESC" if sort_ctx["direction"] == "desc" else "ASC"
        if column == "o.ID":
            return f"o.ID {direction}"
        return f"{column} {direction}, o.ID {direction}"

    def _resolve_member_ids(self, q_member_id):
        """会員コードの部分一致を、注文が持つ会員ID（文字列）の一覧に置き換える。

        JP_MM_MEMBER.ID は decimal、JP_OM_ORDERS.MEMBER_ID は varchar なので、
        この 2 つを結合すると MySQL は数値比較に倒し、注文側の会員IDインデックスを
        使えない。結果 87 万件を全部読んでから会員名で捨てることになり 95 秒かかる。
        先に会員を引いて IN 句に文字列で並べれば注文側のインデックスが効き、
        同じ結果が 0.2 秒で返る。

        該当会員が多すぎるときは None を返し、呼び出し側は従来の結合に戻す。
        """
        if q_member_id in self._member_id_cache:
            return self._member_id_cache[q_member_id]

        sql = f"""
            SELECT CAST(m.ID AS CHAR)
            FROM {LEGACY_MEMBER_TABLE} m
            WHERE m.MEMBER_NO LIKE %s
            LIMIT %s
        """
        with connections["rds"].cursor() as cursor:
            try:
                cursor.execute(sql, [f"%{q_member_id}%", MEMBER_MATCH_LIMIT + 1])
                member_ids = [row[0] for row in cursor.fetchall()]
            except ProgrammingError as exc:
                if is_missing_table_error(exc):
                    logger.info("旧システム会員テーブルが未作成です。table=%s", LEGACY_MEMBER_TABLE)
                    member_ids = None
                else:
                    raise

        if member_ids is not None and len(member_ids) > MEMBER_MATCH_LIMIT:
            member_ids = None

        self._member_id_cache[q_member_id] = member_ids
        return member_ids

    def _needs_member_join(self, sort_key="", **filters):
        """会員テーブルの結合が要るか。

        会員コードで並べるときと、会員が多すぎて IN 句に展開できなかったときだけ
        必要。87 万件に対する無駄な結合を避けるため、それ以外では結合しない。
        """
        if sort_key == "member_no":
            return True

        q_member_id = filters.get("q_member_id")
        if not q_member_id:
            return False
        return self._resolve_member_ids(q_member_id) is None

    def _use_no_order_index_hint(self, **filters):
        """並び替えに主キーを使わせないヒントを付けるか。

        MySQL は「ID 順に逆走査すればすぐ 200 件そろう」と見積もって主キーを選ぶが、
        絞り込みがあると見積もりが実際と桁違いにずれる（15.7 万件の年指定を 540 件と
        見積もる）。1 本のインデックスで絞れる条件があるときは、そのインデックスで
        絞ってから並べた方が速い（注文年 2019 で 38 秒 → 2.6 秒、注文番号の部分一致で
        63 秒 → 16 秒）。

        氏名だけは FIRSTNAME か LASTNAME のどちらかなので 1 本では絞れず、
        ヒントを付けると逆に 0.3 秒から 82 秒に落ちるので付けない。
        """
        if filters.get("q_name"):
            return False

        return bool(
            filters.get("q_order_code")
            or filters.get("q_member_id")
            or filters.get("q_order_statuses")
            or filters.get("q_order_types")
            or self._has_order_date_condition(**filters)
        )

    @staticmethod
    def _has_order_date_condition(**filters):
        """注文日で絞り込まれるか。_build_where が付ける条件と対応させる。"""
        if filters.get("q_order_from") or filters.get("q_order_to"):
            return True

        year, month = parse_order_month(filters.get("target_month"))
        return order_date_range(year, month) is not None

    def _build_where(
        self,
        q_order_code="",
        q_member_id="",
        q_name="",
        q_order_statuses=None,
        q_order_types=None,
        q_order_from="",
        q_order_to="",
        target_month="",
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
            member_ids = self._resolve_member_ids(q_member_id)
            if member_ids is None:
                where.append("m.MEMBER_NO LIKE %s")
                params.append(f"%{q_member_id}%")
            elif not member_ids:
                where.append("1 = 0")
            else:
                placeholders = ", ".join(["%s"] * len(member_ids))
                where.append(f"o.MEMBER_ID IN ({placeholders})")
                params.extend(member_ids)

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

        date_range = order_date_range(*parse_order_month(target_month))
        if date_range:
            where.append("o.ORDER_DATE >= %s AND o.ORDER_DATE < %s")
            params.extend(date_range)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        return where_sql, params

    def _total_count_cache_key(self, **filters):
        signature = json.dumps(filters, sort_keys=True, default=str)
        digest = hashlib.md5(signature.encode("utf-8")).hexdigest()
        version = cache.get(self.TOTAL_COUNT_CACHE_VERSION_KEY, 1)
        return f"legacy_orders:total_count:{version}:{digest}"

    def _invalidate_total_count_cache(self):
        try:
            cache.incr(self.TOTAL_COUNT_CACHE_VERSION_KEY)
        except ValueError:
            cache.set(self.TOTAL_COUNT_CACHE_VERSION_KEY, 2, None)

    def _fetch_total_count(self, **filters):
        """一覧の総件数を返す。

        JP_OM_ORDERS は 87 万件・200MB あり、インデックスで数えられない条件だと
        COUNT(*) だけで 7 秒前後、氏名の部分一致では 80 秒かかる。旧システムからの
        移行コピーで再取込のときしか中身が変わらないので、条件ごとに現行 orders より
        長めにキャッシュする。
        """
        cache_key = self._total_count_cache_key(**filters)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        where_sql, params = self._build_where(**filters)
        # 件数だけなら会員名は要らない。87万件に対する無駄な結合を避けるため、
        # 会員を IN 句に展開できなかったときだけ JOIN する。
        join_sql = MEMBER_JOIN_SQL if self._needs_member_join(**filters) else ""
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

    def _fetch_rows(self, limit=200, offset=0, sort_ctx=None, **filters):
        """1 ページ分を取得する。

        1 行が最大 10KB を超える横に広いテーブルなので、まず ID だけを並べて
        1 ページ分に絞り、その 200 件だけ本体を読む。並び替えの対象から広い行を
        外すことで、既定表示が 32 秒から 0.3 秒になる。
        """
        sort_ctx = sort_ctx or {"sort": "id", "direction": "desc"}
        where_sql, params = self._build_where(**filters)
        order_by = self._build_order_by(sort_ctx)

        page_join_sql = (
            MEMBER_JOIN_SQL
            if self._needs_member_join(sort_ctx["sort"], **filters)
            else ""
        )
        hint = (
            "/*+ NO_ORDER_INDEX(o PRIMARY) */"
            if self._use_no_order_index_hint(**filters)
            else ""
        )

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
                o.BONUS_DATE AS bonus_date,
                o.CREATE_DATE AS created_at
            FROM (
                SELECT {hint} o.ID
                FROM {LEGACY_ORDERS_TABLE} o
                {page_join_sql}
                {where_sql}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            ) AS page
            JOIN {LEGACY_ORDERS_TABLE} o
              ON o.ID = page.ID
            {MEMBER_JOIN_SQL}
            ORDER BY {order_by}
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
            bonus_date = row.get("bonus_date")
            if isinstance(bonus_date, datetime):
                row["bonus_date_input"] = bonus_date.strftime("%Y-%m-%dT%H:%M:%S")
            elif isinstance(bonus_date, date):
                row["bonus_date_input"] = bonus_date.strftime("%Y-%m-%dT00:00")
            else:
                row["bonus_date_input"] = bonus_date or ""
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
            "target_month": (self.request.GET.get("target_month") or "").strip(),
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
                sort_ctx=sort_ctx,
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
        ctx["selected_month"] = filters["target_month"]
        ctx["month_choices"] = self._get_month_choices()
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
            "target_month",
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

    @staticmethod
    def _parse_decimal(value, label):
        text = (value or "").strip().replace(",", "")
        if not text:
            raise ValueError(f"{label}を入力してください。")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"{label}は数値で入力してください。") from exc
        if not parsed.is_finite():
            raise ValueError(f"{label}は有限の数値で入力してください。")
        return parsed

    @staticmethod
    def _parse_bonus_date(value):
        text = (value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("ボーナス計算対象日が不正です。") from exc

    @staticmethod
    def _redirect_url(request):
        next_query = (request.POST.get("next_query") or "").strip()
        url = reverse("connect:legacy_orders")
        return f"{url}?{next_query}" if next_query else url

    def post(self, request, *args, **kwargs):
        user_access = get_user_access(request.user)
        if not user_access.can_menu("legacy_orders") or not user_access.can_update:
            return HttpResponse("権限がありません。", status=403)

        redirect_url = self._redirect_url(request)
        if (request.POST.get("action") or "").strip() != "update":
            messages.error(request, "不正な操作です。")
            return redirect(redirect_url)

        try:
            order_id = int((request.POST.get("id") or "").strip())
            order_status = (request.POST.get("order_status") or "").strip()
            order_type = (request.POST.get("order_type") or "").strip()
            order_year = int((request.POST.get("order_year") or "").strip())
            order_month = int((request.POST.get("order_month") or "").strip())
            order_name = (request.POST.get("order_name") or "").strip()
            total_price = self._parse_decimal(
                request.POST.get("total_price"), "購入合計金額"
            )
            total_bv = self._parse_decimal(request.POST.get("total_bv"), "合計BV")
            bonus_date = self._parse_bonus_date(request.POST.get("bonus_date"))

            if order_status not in ORDER_STATUS_LABELS:
                raise ValueError("注文状況が不正です。")
            if order_type not in ORDER_TYPE_LABELS:
                raise ValueError("注文区分が不正です。")
            if not MIN_ORDER_YEAR <= order_year <= MAX_ORDER_YEAR:
                raise ValueError("注文年が不正です。")
            if not 1 <= order_month <= 12:
                raise ValueError("注文月が不正です。")
        except (TypeError, ValueError) as exc:
            messages.error(request, str(exc) or "入力内容が不正です。")
            return redirect(redirect_url)

        before_row = fetch_one_dict(
            "rds",
            f"""
                SELECT
                    ID,
                    DOC_NO,
                    ORDER_STATUS,
                    ORDER_TYPE,
                    ORDER_DATE,
                    FIRSTNAME,
                    TOTAL_NET_AMOUNT,
                    TOTAL_BV,
                    BONUS_DATE
                FROM {LEGACY_ORDERS_TABLE}
                WHERE ID = %s
                LIMIT 1
            """,
            [order_id],
        )
        if not before_row:
            messages.error(request, "更新対象データが見つかりませんでした。")
            return redirect(redirect_url)

        current_order_date = before_row.get("ORDER_DATE")
        current_day = getattr(current_order_date, "day", 1)
        order_day = min(current_day, monthrange(order_year, order_month)[1])
        if isinstance(current_order_date, (date, datetime)):
            order_date = current_order_date.replace(
                year=order_year,
                month=order_month,
                day=order_day,
            )
        else:
            order_date = date(order_year, order_month, order_day)

        after_row = dict(before_row)
        after_row.update(
            {
                "ORDER_STATUS": order_status,
                "ORDER_TYPE": order_type,
                "ORDER_DATE": order_date,
                "FIRSTNAME": order_name,
                "TOTAL_NET_AMOUNT": total_price,
                "TOTAL_BV": total_bv,
                "BONUS_DATE": bonus_date,
            }
        )

        try:
            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.execute(
                        f"""
                            UPDATE {LEGACY_ORDERS_TABLE}
                            SET
                                ORDER_STATUS = %s,
                                ORDER_TYPE = %s,
                                ORDER_DATE = %s,
                                FIRSTNAME = %s,
                                TOTAL_NET_AMOUNT = %s,
                                TOTAL_BV = %s,
                                BONUS_DATE = %s
                            WHERE ID = %s
                        """,
                        [
                            order_status,
                            order_type,
                            order_date,
                            order_name,
                            total_price,
                            total_bv,
                            bonus_date,
                            order_id,
                        ],
                    )
                    updated_count = cursor.rowcount

                if updated_count:
                    record_change_audit(
                        request,
                        screen_name="旧BONUS_SYSTEM(リンパ) 注文一覧",
                        action_type="update",
                        target_table="JP_OM_ORDERS",
                        target_pk=order_id,
                        summary=f"注文番号 {before_row.get('DOC_NO')} を更新",
                        before_values=before_row,
                        after_values=after_row,
                    )

            if updated_count:
                self._invalidate_total_count_cache()
                messages.success(request, "注文情報を更新しました。")
            else:
                messages.info(request, "注文情報は変更されていません。")
        except Exception:
            logger.exception("旧システム注文一覧の更新に失敗しました。id=%s", order_id)
            messages.error(request, "注文情報の更新中にエラーが発生しました。")

        return redirect(redirect_url)


class LegacyOrdersExportView(LegacyOrdersView):
    """絞り込み条件そのままで Excel 出力する。

    ID が主キーなので、キーセット送り（WHERE o.ID < 直前の最小 ID）は
    主キーの範囲走査で済む。チャンクは上限と同じ 1 回で取り切る。
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
        "ボーナス計算対象日",
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
                o.BONUS_DATE,
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
            return as_db_datetime(value)
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
            return db_datetime(value)
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
