from django.shortcuts import render
# Create your views here.
from django.contrib.auth.views import LoginView
from allauth.account.forms import LoginForm
from django.http import JsonResponse
import logging
from django.views import generic
from django.contrib import messages
from .forms import InquiryForm
from django.urls import reverse_lazy
from django.shortcuts import render
from datetime import date
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.conf import settings
from django.db import connections, transaction
from django.shortcuts import redirect
import math
from urllib.parse import urlencode
from django.db import connections, transaction, IntegrityError
import traceback
from django.http import HttpResponse
from openpyxl import Workbook

from django.db.models import Sum
from django.utils.timezone import make_aware
from .models import Plan, PlanDate, GenreList, Region, FavoritePlan

from .models import TitleMaster, PeriodMaster, UserTitles, Orders, User, PurchaseInfoList
from .models import Settings


logger = logging.getLogger(__name__)


class IndexView(LoginView):
    template_name = "account/login.html"
    form_class = LoginForm


class DriveBonusView(generic.ListView):
    template_name = "drive_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster

    def get_queryset(self):
        return PeriodMaster.objects.using("rds").all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")
        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        # 期別マスタ取得（ここはORMのまま）
        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        print(period)

        st_date = period.st_date
        end_date = period.end_date

        # 日付 -> datetime範囲（開始は00:00:00、終了は翌日00:00:00未満）
        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        # kibetu 例: 2026C01W3 → 2026-01-01 00:00:00
        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])
        rank_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))

        #期別の前の月の年と月を取得
        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_year = prev_month_last.year
        prev_month = prev_month_last.month


        sql = """
WITH RECURSIVE

repurchase_list AS (  -- 再購入リスト
    SELECT
        b.jwoa_code AS distribution_jwoa_code,
        a.bv_actived_flg,
        a.deposit_at,
        a.order_status,
        a.order_type,
        b.distribution_bv,
        CASE -- 101:再購入
            WHEN a.order_type = 101
                THEN LEAST(IFNULL(b.distribution_bv, 0), 50)
            ELSE
                IFNULL(b.distribution_bv, 0)
        END AS custom_bv
    FROM bonus_db.orders AS a
    LEFT JOIN bonus_db.orders_distribution_bv AS b
      ON a.order_code = b.order_code
     -- 101:再購入, 102:初回購入, 103:ランクアップ購入品
    WHERE a.order_type = 101
      AND a.order_status NOT IN (201, 206)
      AND a.deposit_at >= %s
      AND a.deposit_at < %s

    UNION ALL

    SELECT
        member_no AS distribution_jwoa_code,
        1         AS bv_actived_flg,
        payment_date AS deposit_at,
        203       AS order_status,
        105       AS order_type,-- 105:特別対応
        total_bv  AS distribution_bv,
        LEAST(IFNULL(total_bv, 0), 50) AS custom_bv
    FROM bonus_db.api_users_bv
    WHERE payment_date >= %s
      AND payment_date < %s
),


-- ランクアップ、初回購入情報リスト
rank_up_list AS (
    SELECT
        b.jwoa_code AS distribution_jwoa_code,
        a.bv_actived_flg,
        a.deposit_at,
        a.order_status,
        a.order_type,
        b.distribution_bv,
        IFNULL(b.distribution_bv, 0) AS custom_bv
    FROM bonus_db.orders AS a
    LEFT JOIN bonus_db.orders_distribution_bv AS b
      ON a.order_code = b.order_code
     -- 101:再購入, 102:初回購入, 103:ランクアップ購入品
    WHERE a.order_type IN (102, 103)
      AND a.order_status NOT IN (201, 206)
      AND a.deposit_at >= %s
      AND a.deposit_at < %s
),
-- 購入者リスト
purchasers_list AS (
select distribution_jwoa_code as jwoa_code from repurchase_list
union
select distribution_jwoa_code as jwoa_code from rank_up_list
),

/* ランクアップ変動履歴 */
rankup_history AS (
  SELECT *
  FROM (
      SELECT
          t.*,
          ROW_NUMBER() OVER (
              PARTITION BY user_id
              ORDER BY fluctuation_up_at DESC
          ) AS rn
      FROM bonus_db.users_rank_up_history AS t
      WHERE fluctuation_up_at < %s
  ) x
  WHERE rn = 1
),

-- ユーザー(in_購入者リスト)
user_in_purchasers_list AS (
  SELECT u.*
  FROM bonus_db.users_target_rank AS u
  JOIN purchasers_list AS p
    ON p.jwoa_code = u.jmoa_code
),


-- 再起処理
chain AS (
    -- 1段目：各ユーザーの紹介者を起点にする
    SELECT
        u.jmoa_code        AS jmoa_code,
        u.new_rank             AS jmoa_rank,
        u.introducer_code  AS current_code,
        1                  AS lvl
    FROM user_in_purchasers_list AS u

    UNION ALL

    -- 2段目以降：紹介者を辿る（紹介者が rank=9 の間だけ上へ進む）
    SELECT
        c.jmoa_code        AS jmoa_code,
        c.jmoa_rank        AS jmoa_rank,
        up.introducer_code AS current_code,
        c.lvl + 1          AS lvl
    FROM chain AS c
    JOIN bonus_db.users_target_rank AS up
      ON up.jmoa_code = c.current_code
    WHERE
        c.current_code IS NOT NULL
        AND up.new_rank = 9
        AND c.lvl < 100
),

last_step AS (
    -- 各ユーザーごとに、辿れた最終段（最大lvl）を取る
    SELECT
        chain.jmoa_code AS jmoa_code,
        MAX(chain.lvl)  AS max_lvl
    FROM chain
    GROUP BY chain.jmoa_code
),

-- 一般会員を除く紹介者を再帰的に設定
-- 全購入者情報
user_introducer_non9 AS (
SELECT
    c.current_code   AS introducer_code,
    u2.new_rank          AS introducer_rank,
    c.jmoa_code      AS jmoa_code,
    c.jmoa_rank      AS jmoa_rank,
    c.lvl            AS lvl
FROM chain AS c
JOIN last_step AS s
  ON s.jmoa_code = c.jmoa_code
 AND s.max_lvl   = c.lvl
LEFT JOIN bonus_db.users_target_rank AS u2
  ON u2.jmoa_code = c.current_code
),

-- non9にタイトルを追加(全購入者情報)
user_introducer_non9_addTitle AS (
SELECT
    non9.introducer_code,
    non9.introducer_rank,
    non9.jmoa_code,
    u.send_bv_name,
    non9.jmoa_rank,
    non9.lvl,
    tm.title_id as introducer_title_id,
    tm.title_name as introducer_title_name
FROM user_introducer_non9 AS non9
LEFT JOIN bonus_db.users_target_rank ui
    ON non9.introducer_code = ui.jmoa_code
LEFT JOIN bonus_db.user_titles ut
    ON ut.jmoa_code = ui.jmoa_code
LEFT JOIN bonus_db.title_master tm
    ON ut.title_id = tm.title_id
LEFT JOIN bonus_db.users_target_rank u
    ON non9.jmoa_code = u.jmoa_code
),


-- ランクアップ、初回購入情報
rank_up_add_non9_addTitle AS (
    SELECT
        non9.introducer_title_name as title_name,
        non9.introducer_code,
        non9.jmoa_code as jwoa_code,
        non9.send_bv_name as jwoa_name,
        rank_up.custom_bv,
        CASE
            WHEN non9.introducer_title_id >= 4
                THEN TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.20, 2)

            WHEN non9.introducer_title_id = 3
                THEN TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.15, 2)

            ELSE
                TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.10, 2)
        END AS bonus_amount
    FROM rank_up_list AS rank_up
    LEFT JOIN user_introducer_non9_addTitle AS non9
      ON rank_up.distribution_jwoa_code = non9.jmoa_code
    where rank_up.custom_bv > 0
),






-- 条件を満たす紹介者（rank!=9 & bv>=50）が見つかるまで上へ辿る
chain_find AS (
    -- 1段目：最初に評価する紹介者 = u.introducer_code
    SELECT
        u.jmoa_code       AS jmoa_code,
        u.new_rank            AS jmoa_rank,
        u.introducer_code AS evaluated_code,
        1                 AS lvl,
        CASE
            WHEN up.new_rank <> 9 AND IFNULL(p.bv, 0) >= 50 THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM user_in_purchasers_list u
    LEFT JOIN bonus_db.users_target_rank up
      ON up.jmoa_code = u.introducer_code
    LEFT JOIN bonus_db.purchase_info_list p
      ON p.jwoa_code = up.jmoa_code
     AND p.year  = %s
     AND p.month = %s

    UNION ALL

    -- 2段目以降
    SELECT
        c.jmoa_code,
        c.jmoa_rank,
        c.next_code       AS evaluated_code,
        c.lvl + 1         AS lvl,
        CASE
            WHEN up.new_rank <> 9 AND IFNULL(p.bv, 0) >= 50 THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM chain_find c
    JOIN bonus_db.users_target_rank up
      ON up.jmoa_code = c.next_code
    LEFT JOIN bonus_db.purchase_info_list p
      ON p.jwoa_code = up.jmoa_code
     AND p.year  = %s
     AND p.month = %s
    WHERE c.next_code IS NOT NULL
      AND c.found = 0
      AND c.lvl < 100
),

first_found AS (
    SELECT
        jmoa_code,
        MIN(lvl) AS hit_lvl
    FROM chain_find
    WHERE found = 1
    GROUP BY jmoa_code
),

-- 一般会員以外 & 前月再購入
user_introducer_non9_2 AS (
SELECT
    c.evaluated_code AS introducer_code,
    u.new_rank           AS introducer_rank,
    c.jmoa_code,
    c.jmoa_rank,
    p.bv             AS introducer_bv,
    c.lvl
FROM chain_find c
JOIN first_found f
  ON f.jmoa_code = c.jmoa_code
 AND f.hit_lvl   = c.lvl
JOIN bonus_db.users_target_rank u
  ON u.jmoa_code = c.evaluated_code
JOIN bonus_db.purchase_info_list p
  ON p.jwoa_code = c.evaluated_code
 AND p.year  = %s
 AND p.month = %s
WHERE c.found = 1
ORDER BY c.jmoa_code
),

-- non9_2にタイトルを追加
user_introducer_non9_2_addTitle AS (
SELECT
    non9.introducer_code,
    non9.introducer_rank,
    non9.jmoa_code,
    u.send_bv_name,
    non9.jmoa_rank,
    non9.lvl,
    tm.title_id as introducer_title_id,
    tm.title_name as introducer_title_name
FROM user_introducer_non9_2 AS non9
LEFT JOIN bonus_db.users_target_rank ui
    ON non9.introducer_code = ui.jmoa_code
LEFT JOIN bonus_db.user_titles ut
    ON ut.jmoa_code = ui.jmoa_code
LEFT JOIN bonus_db.title_master tm
    ON ut.title_id = tm.title_id
LEFT JOIN bonus_db.users_target_rank u
    ON non9.jmoa_code = u.jmoa_code
),

-- 再購入情報
repurchase_add_non9_2_addTitle AS (
    SELECT
        non9.introducer_title_name as title_name,
        non9.introducer_code,
        non9.jmoa_code as jwoa_code,
        non9.send_bv_name as jwoa_name,
        repurchase.custom_bv,
        CASE
            WHEN non9.introducer_title_id >= 4
                THEN TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.20, 2)

            WHEN non9.introducer_title_id = 3
                THEN TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.15, 2)

            ELSE
                TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.10, 2)
        END AS bonus_amount
    FROM repurchase_list AS repurchase
    LEFT JOIN user_introducer_non9_2_addTitle AS non9
      ON repurchase.distribution_jwoa_code = non9.jmoa_code
    where repurchase.custom_bv > 0
),

pay_drive_list AS (
select * from rank_up_add_non9_addTitle
union all
select * from repurchase_add_non9_2_addTitle
)

select * from pay_drive_list order by introducer_code, jwoa_code
        """



        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [start_dt, end_dt, start_dt, end_dt, start_dt, end_dt, rank_dt, prev_year, prev_month, prev_year, prev_month, prev_year, prev_month])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # テンプレに渡す
        ctx["rows"] = rows
        return ctx


class InquiryView(generic.FormView):
    template_name = "inquiry.html"
    form_class = InquiryForm
    success_url = reverse_lazy('connect:inquiry')

    def form_valid(self, form):
        form.send_email()
        messages.info(self.request, f'メッセージを送信しました')
        logger.info('Inquiry sent by {}'.format(form.cleaned_data['name']))
        return super().form_valid(form)


class PlanListView(generic.ListView):
    template_name = 'plan_list.html'
    paginate_by = 2

    def get(self, request, *args, **kwargs):
        form_data = {
            'genre_name': request.GET.get('checkbox_value[]'),
            'event_place': request.GET.get('place_checkbox_value[]'),
            'event_date': request.GET.get('event_date[]'),
            'gender': request.GET.get('gender_value[]'),
            'age': request.GET.get('form_field_age[]'),
        }

        current_date_time = datetime.now()
        reservation_limit_hours = current_date_time + timedelta(hours=settings.RESERVATION_LIMIT_HOURS)

        filter_conditions = []

        # ジャンル名があれば条件を追加
        if form_data['genre_name']:
            array_genre_name = form_data['genre_name'].split(', ')
            filter_conditions.append(Q(plan_name__genre_name__in=array_genre_name))

        # 日付があれば条件を追加
        if form_data['event_date']:
            date_strings = form_data['event_date'].split(', ')
            dates = [datetime.strptime(date_str, '%Y/%m/%d').date() for date_str in date_strings]
            filter_conditions.append(Q(start_time__date__in=dates))

        # イベント場所があれば条件を追加
        if form_data['event_place']:
            array_place = form_data['event_place'].split(', ')
            filter_conditions.append(Q(plan_name__place__in=array_place))

        # 性別があれば条件を追加
        if form_data['gender']:
            if form_data['gender'] == "0":
                filter_conditions.append(Q(plan_name__gender_limit=Plan.FEMALE))
            elif form_data['gender'] == "1":
                filter_conditions.append(Q(plan_name__gender_limit=Plan.MALE))

        # 年齢制限があれば条件を追加
        if form_data['age']:
            filter_conditions.append(Q(plan_name__min_age__lte=form_data['age']) | Q(plan_name__min_age__isnull=True))
            filter_conditions.append(Q(plan_name__max_age__gte=form_data['age']) | Q(plan_name__max_age__isnull=True))

        combined_conditions = Q()
        for condition in filter_conditions:
            combined_conditions &= condition

        queryset = (
            PlanDate.objects
            .select_related('plan_name__genre_name')
            .filter(plan_name__plan_active=True, start_time__gte=reservation_limit_hours)
            .filter(combined_conditions)
        )

        #お気に入りリストを取得する
        user_id = request.user.id
        favorite_plan_list = FavoritePlan.objects.filter(username=user_id).values_list('plan_date', flat=True)

        return render(request, self.template_name, {'plan_list': queryset, 'favorite_list': favorite_plan_list})


class AddFavoriteToDBView(generic.View):
    def post(self, request):
        plan_id = request.POST.get('plan_id')
        user_id = request.user.id

        if user_id is None:
            return JsonResponse({'status': 'user_none'})

        # 指定されたplan_date_idとusernameの組み合わせが既に存在するかを確認
        existing_favorite = FavoritePlan.objects.filter(plan_date_id=int(plan_id), username=user_id).first()

        if existing_favorite:
            # 既に存在する場合は削除
            existing_favorite.delete()
        else:
            # 存在しない場合は追加
            FavoritePlan.objects.create(plan_date_id=int(plan_id), username_id=user_id)

        return JsonResponse({'status': 'success'})  # もしくはエラーメッセージを返すことも可能


class PlanDetailView(generic.DetailView):
    model = PlanDate
    template_name = 'plan_detail.html'

    def get_queryset(self):
        # self.kwargs['pk']を使ってpkの値を取得
        pk = self.kwargs.get('pk')

        # pkを条件にクエリセットをフィルタリングする例
        queryset = PlanDate.objects.filter(id=pk)
        return queryset



class KibetuView(generic.ListView):
    template_name = "kibetu.html"
    context_object_name = "rows"
    model = PeriodMaster  # kibetu, st_date, end_date を持つモデル

    def get_queryset(self):
        qs = PeriodMaster.objects.using("rds").all()

        selected_kibetu = (self.request.GET.get("kibetu") or "").strip()   # 完全一致用
        q_kibetu = (self.request.GET.get("q_kibetu") or "").strip()        # 部分一致用

        if selected_kibetu:
            qs = qs.filter(kibetu=selected_kibetu)

        if q_kibetu:
            qs = qs.filter(kibetu__icontains=q_kibetu)

        return qs.order_by("-st_date", "-kibetu")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx["selected_kibetu"] = (self.request.GET.get("kibetu") or "").strip()
        ctx["q_kibetu"] = (self.request.GET.get("q_kibetu") or "").strip()

        # プルダウンの選択肢（重複なし）
        ctx["kibetu_choices"] = list(
            PeriodMaster.objects.using("rds")
            .order_by("-st_date")
            .values_list("kibetu", flat=True)
            .distinct()
        )

        return ctx


class TitleListView(generic.ListView):
    template_name = "title_list.html"
    context_object_name = "rows"
    model = TitleMaster

    def get_queryset(self):
        # 並び順はお好みで（title_id順など）
        return TitleMaster.objects.using("rds").order_by("title_id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # 件数表示用（テンプレで rows|length を使わない）
        ctx["total_count"] = ctx["rows"].count()
        return ctx



class RepurchaseListView(generic.TemplateView):
    template_name = "repurchase_list.html"

    def _fetch_rows(
        self,
        year=None,
        month=None,
        q_code: str = "",
        q_name: str = "",
        q_order_code: str = "",
        q_order_type: str = "",
    ):
        sql = """
SELECT *
FROM bonus_db.purchase_info_list
WHERE 1=1
"""
        params = []

        # 月指定がある場合のみ絞り込み
        if year is not None and month is not None:
            sql += """
  AND year = %s
  AND month = %s
"""
            params.extend([year, month])

        # jwoa_code 検索
        if q_code:
            sql += "  AND jwoa_code LIKE %s\n"
            params.append(f"%{q_code}%")

        # send_bv_name 検索
        if q_name:
            sql += "  AND send_bv_name LIKE %s\n"
            params.append(f"%{q_name}%")

        # order_code 検索
        if q_order_code:
            sql += "  AND order_code LIKE %s\n"
            params.append(f"%{q_order_code}%")

        # 注文区分 検索
        if q_order_type:
            sql += "  AND order_type = %s\n"
            params.append(q_order_type)

        sql += """
ORDER BY bv DESC, jwoa_code ASC
LIMIT 2000
"""

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            print(cursor._executed)  # デバッグ用
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def _get_month_choices(self):
        today = date.today().replace(day=1)

        return [
            {
                "value": (today - relativedelta(months=i)).strftime("%Y-%m"),
                "year": (today - relativedelta(months=i)).year,
                "month": (today - relativedelta(months=i)).month,
            }
            for i in range(12)
        ]

    def _count_rows(
        self,
        year=None,
        month=None,
        q_code: str = "",
        q_name: str = "",
        q_order_code: str = "",
        q_order_type: str = "",
    ):
        sql = """
    SELECT COUNT(*) AS cnt
    FROM bonus_db.purchase_info_list
    WHERE 1=1
    """
        params = []

        if year is not None and month is not None:
            sql += """
      AND year = %s
      AND month = %s
    """
            params.extend([year, month])

        if q_code:
            sql += "  AND jwoa_code LIKE %s\n"
            params.append(f"%{q_code}%")

        if q_name:
            sql += "  AND send_bv_name LIKE %s\n"
            params.append(f"%{q_name}%")

        if q_order_code:
            sql += "  AND send_bv_name LIKE %s\n"
            params.append(f"%{q_order_code}%")

        if q_order_type:
            sql += "  AND order_type = %s\n"
            params.append(q_order_type)

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_month = (self.request.GET.get("prev_month") or "").strip()
        q_code = (self.request.GET.get("q_code") or "").strip()
        q_name = (self.request.GET.get("q_name") or "").strip()
        q_order_code = (self.request.GET.get("q_order_code") or "").strip()
        q_order_type = (self.request.GET.get("q_order_type") or "").strip()

        ctx["month_choices"] = self._get_month_choices()
        ctx["selected_prev_month"] = selected_month
        ctx["q_code"] = q_code
        ctx["q_name"] = q_name
        ctx["q_order_code"] = q_order_code
        ctx["q_order_type"] = q_order_type

        ctx["rows"] = []
        ctx["selected_period"] = None
        ctx["total_count"] = 0

        if not selected_month:
            ctx["rows"] = self._fetch_rows(
                q_code=q_code,
                q_name=q_name,
                q_order_code=q_order_code,
                q_order_type=q_order_type,
            )
            ctx["total_count"] = self._count_rows(
                q_code=q_code,
                q_name=q_name,
                q_order_code=q_order_code,
                q_order_type=q_order_type,
            )
            return ctx

        try:
            y, m = map(int, selected_month.split("-"))
        except ValueError:
            return ctx

        ctx["selected_period"] = {"year": y, "month": m}

        ctx["rows"] = self._fetch_rows(
            year=y,
            month=m,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
        )
        ctx["total_count"] = self._count_rows(
            year=y,
            month=m,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
        )

        return ctx

class SettingsView(generic.ListView):
    template_name = "settings.html"
    context_object_name = "rows"
    model = Settings

    def get_queryset(self):
        # 並び順はお好みで（title_id順など）
        return Settings.objects.using("rds").order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # 件数表示用（テンプレで rows|length を使わない）
        ctx["total_count"] = ctx["rows"].count()
        return ctx



class UserTargetRankView(generic.TemplateView):
    template_name = "user_target_rank.html"

    # 表示カラム（順番固定）
    DISPLAY_COLUMNS = [
        "id",
        "jmoa_code",
        "introducer_code",
        "placement_code",
        "group_code",
        "send_bv_name",
        "status_code",
        "rank",
        "salon_administrator",
        "salon_name",
        "interim_at",
        "activated_at",
        "created_at",
        "target_rank",
        "max_up_at",
        "new_rank",
    ]

    # ----------------------------
    # UI: 月リスト
    # ----------------------------
    def get_month_list(self):
        today = date.today().replace(day=1)
        months = []
        for i in range(0, 13):  # 今月〜過去12ヶ月
            d = today - relativedelta(months=i)
            months.append({
                "value": f"{d.year}-{d.month:02d}",
                "year": d.year,
                "month": d.month,
            })
        return months

    def _month_end_exclusive(self, year: int, month: int):
        """対象月の締め（翌月1日00:00:00）"""
        base = datetime(year, month, 1, 0, 0, 0)
        return base + relativedelta(months=1)

    # ----------------------------
    # ✅ 件数（総数）
    # ----------------------------
    def _fetch_total_count(self) -> int:
        sql = "SELECT COUNT(*) FROM bonus_db.users"
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql)
            return int(cursor.fetchone()[0])

    # ----------------------------
    # 表示用: LIMITあり
    # ----------------------------
    def _fetch_users(self, cutoff_dt: datetime, limit: int = 100):
        sql = f"""
    SELECT
      t.id,
      t.jmoa_code,
      t.introducer_code,
      t.placement_code,
      t.group_code,
      t.send_bv_name,
      t.status_code,
      t.`rank`,
      t.salon_administrator,
      t.salon_name,
      t.interim_at,
      t.activated_at,
      t.created_at,

      CASE
        WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
        ELSE NULL
      END AS target_rank,

      x.created_at AS max_up_at,

      CASE
        WHEN t.status_code <> 1 THEN 9
        WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
        ELSE t.`rank`
      END AS new_rank

    FROM bonus_db.users t
    LEFT JOIN (
      SELECT user_id, fluctuation_name, created_at
      FROM (
        SELECT
          user_id,
          fluctuation_name,
          created_at,
          ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY created_at DESC, id DESC
          ) AS rn
        FROM bonus_db.users_rank_up_history
        WHERE created_at <= %s
      ) r
      WHERE rn = 1
    ) x
    ON t.jmoa_code = x.user_id
    ORDER BY t.jmoa_code
    LIMIT {int(limit)}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [cutoff_dt])
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    # ----------------------------
    # GET: 画面表示
    # ----------------------------
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx["month_list"] = self.get_month_list()
        ctx["selected_prev_month"] = self.request.GET.get("prev_month") or ""
        ctx["selected_period"] = None

        ctx["columns"] = self.DISPLAY_COLUMNS
        ctx["rows"] = []
        ctx["total_count"] = 0  # ✅ 追加（本当の件数）

        #登録月を設定
        with connections["rds"].cursor() as cursor:
            cursor.execute("""
                SELECT value
                FROM bonus_db.settings
                WHERE name = 'user_add_rank'
                LIMIT 1
            """)
            row = cursor.fetchone()

        ctx["select_month"] = row[0] if row else ""

        if not ctx["selected_prev_month"]:
            return ctx

        y, m = map(int, ctx["selected_prev_month"].split("-"))
        ctx["selected_period"] = {"year": y, "month": m}

        cutoff_dt = self._month_end_exclusive(y, m)

        # ✅ 表示は100件、件数は全件
        ctx["rows"] = self._fetch_users(cutoff_dt, limit=100)
        ctx["total_count"] = self._fetch_total_count()




        return ctx

    # ----------------------------
    # POST: 登録（LIMITなしで全件UPSERT）
    # ----------------------------
    def post(self, request, *args, **kwargs):
        selected_prev_month = request.POST.get("prev_month") or ""
        if not selected_prev_month:
            messages.error(request, "対象年月が未選択です。")
            return redirect("connect:user_target_rank")

        year, month = map(int, selected_prev_month.split("-"))
        cutoff_dt = self._month_end_exclusive(year, month)

        # ✅ settings と users_target_rank.target_rank に入れる「YYYYMM」
        target_rank = f"{year}{month:02d}"   # 例: 202512

        insert_sql = """
    INSERT INTO bonus_db.users_target_rank
    (
      `jmoa_code`,
      `introducer_code`,
      `placement_code`,
      `group_code`,
      `send_bv_name`,
      `status_code`,
      `rank`,
      `salon_administrator`,
      `salon_name`,
      `interim_at`,
      `activated_at`,
      `created_at`,
      `target_rank`,
      `max_up_at`,
      `new_rank`
    )
    SELECT
      t.jmoa_code,
      t.introducer_code,
      t.placement_code,
      t.group_code,
      t.send_bv_name,
      t.status_code,
      t.`rank`,
      t.salon_administrator,
      t.salon_name,
      t.interim_at,
      t.activated_at,
      t.created_at,

      /* target_rank（=履歴のランク）※数値化 */
      CASE
        WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
        ELSE NULL
      END AS target_rank,

      /* max_up_at（=最新ランクアップ日時） */
      x.created_at AS max_up_at,

      /* new_rank（=確定ランク）※数値 */
      CASE
        WHEN t.status_code <> 1 THEN 9
        WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
        ELSE t.`rank`
      END AS new_rank

    FROM bonus_db.users t
    LEFT JOIN (
      SELECT user_id, fluctuation_name, created_at
      FROM (
        SELECT
          user_id,
          fluctuation_name,
          created_at,
          ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY created_at DESC, id DESC
          ) AS rn
        FROM bonus_db.users_rank_up_history
        WHERE created_at <= %s
      ) r
      WHERE rn = 1
    ) x
    ON t.jmoa_code = x.user_id
    """

        with connections["rds"].cursor() as cursor:
            # ① 全削除
            cursor.execute("TRUNCATE TABLE bonus_db.users_target_rank")

            # ② 全件INSERT（%s は cutoff_dt だけ）
            cursor.execute(insert_sql, [cutoff_dt])

            # ③ settings更新（user_add_rank の value を YYYYMM に更新）
            cursor.execute(
                """
                UPDATE bonus_db.settings
                SET value = %s
                WHERE name = 'user_add_rank'
                """,
                [target_rank],
            )

        messages.success(request, f"{year}年{month}月（{target_rank}）で全件登録しました。")
        return redirect(f"{redirect('connect:user_target_rank').url}?prev_month={selected_prev_month}")


class TitleUserView(generic.TemplateView):
    template_name = "title_user.html"

    DEFAULT_PER_PAGE = 200
    MAX_PER_PAGE = 500

    def _build_where(self, title_id: str, q_jpid: str):
        where = []
        params = []

        if title_id:
            where.append("ut.title_id = %s")
            params.append(title_id)

        if q_jpid:
            where.append("u.jmoa_code LIKE %s")
            params.append(f"%{q_jpid}%")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        return where_sql, params

    def _fetch_total_count(self, title_id: str, q_jpid: str) -> int:
        where_sql, params = self._build_where(title_id, q_jpid)

        sql = f"""
SELECT COUNT(*)
FROM bonus_db.user_titles ut
LEFT JOIN bonus_db.users u
  ON ut.jmoa_code = u.jmoa_code
{where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.fetchone()[0])

    def _fetch_rows_keyset(
        self,
        title_id: str,
        q_jpid: str,
        limit: int,
        after_title_id: str = "",
        after_jmoa_code: str = "",
    ):
        where_sql, params = self._build_where(title_id, q_jpid)

        keyset_sql = ""
        if after_title_id and after_jmoa_code:
            if where_sql:
                keyset_sql = """
 AND (
      ut.title_id > %s
      OR (ut.title_id = %s AND ut.jmoa_code > %s)
 )
                """
            else:
                keyset_sql = """
WHERE (
      ut.title_id > %s
      OR (ut.title_id = %s AND ut.jmoa_code > %s)
)
                """
            params += [after_title_id, after_title_id, after_jmoa_code]

        sql = f"""
SELECT
  u.jmoa_code AS jmoa_code,
  u.send_bv_name AS jwoa_name,
  ut.title_id AS title_id,
  tm.title_name AS title_name,
  ut.update_date AS update_date
FROM bonus_db.user_titles ut
LEFT JOIN bonus_db.users u
  ON ut.jmoa_code = u.jmoa_code
LEFT JOIN bonus_db.title_master tm
  ON ut.title_id = tm.title_id
{where_sql}
{keyset_sql}
ORDER BY ut.title_id, ut.jmoa_code
LIMIT %s
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params + [limit])
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def _fetch_title_choices(self):
        sql = """
SELECT
  tm.title_id,
  tm.title_name
FROM bonus_db.title_master tm
ORDER BY tm.title_id
        """
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql)
            return [{"title_id": r[0], "title_name": r[1]} for r in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        title_id = (self.request.GET.get("title_id") or "").strip()
        q_jpid = (self.request.GET.get("q_jpid") or "").strip()

        try:
            per_page = int(self.request.GET.get("per_page") or str(self.DEFAULT_PER_PAGE))
        except ValueError:
            per_page = self.DEFAULT_PER_PAGE
        per_page = max(1, min(per_page, self.MAX_PER_PAGE))

        after_title_id = (self.request.GET.get("after_title_id") or "").strip()
        after_jmoa_code = (self.request.GET.get("after_jmoa_code") or "").strip()

        total_count = self._fetch_total_count(title_id, q_jpid)
        total_pages = max(1, math.ceil(total_count / per_page))

        rows = self._fetch_rows_keyset(
            title_id=title_id,
            q_jpid=q_jpid,
            limit=per_page,
            after_title_id=after_title_id,
            after_jmoa_code=after_jmoa_code,
        )

        next_after_title_id = ""
        next_after_jmoa_code = ""
        if rows:
            last = rows[-1]
            next_after_title_id = str(last["title_id"])
            next_after_jmoa_code = str(last["jmoa_code"])

        base_params = {}
        if title_id:
            base_params["title_id"] = title_id
        if q_jpid:
            base_params["q_jpid"] = q_jpid
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        ctx["title_choices"] = self._fetch_title_choices()
        ctx["selected_title_id"] = title_id
        ctx["q_jpid"] = q_jpid

        ctx["rows"] = rows
        ctx["total_count"] = total_count
        ctx["per_page"] = per_page

        # キーセットなので厳密なページ番号ではなく表示用
        current_page = 1
        if after_title_id and after_jmoa_code:
            req_page = self.request.GET.get("page")
            try:
                current_page = max(1, int(req_page)) if req_page else 2
            except ValueError:
                current_page = 2

        ctx["page"] = current_page
        ctx["total_pages"] = total_pages

        ctx["base_qs"] = urlencode(base_params)

        ctx["has_next"] = (
            len(rows) == per_page
            and bool(next_after_title_id)
            and bool(next_after_jmoa_code)
        )
        ctx["next_after_title_id"] = next_after_title_id
        ctx["next_after_jmoa_code"] = next_after_jmoa_code

        ctx["has_prev_hint"] = bool(after_title_id and after_jmoa_code)

        return ctx



class BasicBonusView(generic.ListView):
    template_name = "basic_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster

    def get_queryset(self):
        return PeriodMaster.objects.using("rds").all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")
        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        # 期別マスタ取得（ここはORMのまま）
        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        print(period)

        st_date = period.st_date
        end_date = period.end_date

        # 日付 -> datetime範囲（開始は00:00:00、終了は翌日00:00:00未満）
        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        # kibetu 例: 2026C01W3 → 2026-01-01 00:00:00
        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])
        rank_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))

        #期別の前の月の年と月を取得
        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_year = prev_month_last.year
        prev_month = prev_month_last.month


        sql = """
WITH RECURSIVE

repurchase_list AS (  -- 再購入リスト
    SELECT
        b.jwoa_code AS distribution_jwoa_code,
        a.bv_actived_flg,
        a.deposit_at,
        a.order_status,
        a.order_type,
        b.distribution_bv,
        CASE -- 101:再購入
            WHEN a.order_type = 101
                THEN LEAST(IFNULL(b.distribution_bv, 0), 50)
            ELSE
                IFNULL(b.distribution_bv, 0)
        END AS custom_bv
    FROM bonus_db.orders AS a
    LEFT JOIN bonus_db.orders_distribution_bv AS b
      ON a.order_code = b.order_code
     -- 101:再購入, 102:初回購入, 103:ランクアップ購入品
    WHERE a.order_type = 101
      AND a.order_status NOT IN (201, 206)
      AND a.deposit_at >= %s
      AND a.deposit_at < %s

    UNION ALL

    SELECT
        member_no AS distribution_jwoa_code,
        1         AS bv_actived_flg,
        payment_date AS deposit_at,
        203       AS order_status,
        105       AS order_type,-- 105:特別対応
        total_bv  AS distribution_bv,
        LEAST(IFNULL(total_bv, 0), 50) AS custom_bv
    FROM bonus_db.api_users_bv
    WHERE payment_date >= %s
      AND payment_date < %s
),


-- ランクアップ、初回購入情報リスト
rank_up_list AS (
    SELECT
        b.jwoa_code AS distribution_jwoa_code,
        a.bv_actived_flg,
        a.deposit_at,
        a.order_status,
        a.order_type,
        b.distribution_bv,
        IFNULL(b.distribution_bv, 0) AS custom_bv
    FROM bonus_db.orders AS a
    LEFT JOIN bonus_db.orders_distribution_bv AS b
      ON a.order_code = b.order_code
     -- 101:再購入, 102:初回購入, 103:ランクアップ購入品
    WHERE a.order_type IN (102, 103)
      AND a.order_status NOT IN (201, 206)
      AND a.deposit_at >= %s
      AND a.deposit_at < %s
),
-- 購入者リスト
purchasers_list AS (
select distribution_jwoa_code as jwoa_code from repurchase_list
union
select distribution_jwoa_code as jwoa_code from rank_up_list
),

/* ランクアップ変動履歴 */
rankup_history AS (
  SELECT *
  FROM (
      SELECT
          t.*,
          ROW_NUMBER() OVER (
              PARTITION BY user_id
              ORDER BY fluctuation_up_at DESC
          ) AS rn
      FROM bonus_db.users_rank_up_history AS t
      WHERE fluctuation_up_at < %s
  ) x
  WHERE rn = 1
),

-- ユーザー(in_購入者リスト)
user_in_purchasers_list AS (
  SELECT u.*
  FROM bonus_db.users_target_rank AS u
  JOIN purchasers_list AS p
    ON p.jwoa_code = u.jmoa_code
),


-- 再起処理
chain AS (
    -- 1段目：各ユーザーの紹介者を起点にする
    SELECT
        u.jmoa_code        AS jmoa_code,
        u.new_rank             AS jmoa_rank,
        u.introducer_code  AS current_code,
        1                  AS lvl
    FROM user_in_purchasers_list AS u

    UNION ALL

    -- 2段目以降：紹介者を辿る（紹介者が rank=9 の間だけ上へ進む）
    SELECT
        c.jmoa_code        AS jmoa_code,
        c.jmoa_rank        AS jmoa_rank,
        up.introducer_code AS current_code,
        c.lvl + 1          AS lvl
    FROM chain AS c
    JOIN bonus_db.users_target_rank AS up
      ON up.jmoa_code = c.current_code
    WHERE
        c.current_code IS NOT NULL
        AND up.new_rank = 9
        AND c.lvl < 100
),

last_step AS (
    -- 各ユーザーごとに、辿れた最終段（最大lvl）を取る
    SELECT
        chain.jmoa_code AS jmoa_code,
        MAX(chain.lvl)  AS max_lvl
    FROM chain
    GROUP BY chain.jmoa_code
),

-- 一般会員を除く紹介者を再帰的に設定
user_introducer_non9 AS (
SELECT
    c.current_code   AS introducer_code,
    u2.new_rank          AS introducer_rank,
    c.jmoa_code      AS jmoa_code,
    c.jmoa_rank      AS jmoa_rank,
    c.lvl            AS lvl
FROM chain AS c
JOIN last_step AS s
  ON s.jmoa_code = c.jmoa_code
 AND s.max_lvl   = c.lvl
LEFT JOIN bonus_db.users_target_rank AS u2
  ON u2.jmoa_code = c.current_code
),

-- non9にタイトルを追加
user_introducer_non9_addTitle AS (
SELECT
    non9.introducer_code,
    non9.introducer_rank,
    non9.jmoa_code,
    u.send_bv_name,
    non9.jmoa_rank,
    non9.lvl,
    tm.title_id as introducer_title_id,
    tm.title_name as introducer_title_name
FROM user_introducer_non9 AS non9
LEFT JOIN bonus_db.users_target_rank ui
    ON non9.introducer_code = ui.jmoa_code
LEFT JOIN bonus_db.user_titles ut
    ON ut.jmoa_code = ui.jmoa_code
LEFT JOIN bonus_db.title_master tm
    ON ut.title_id = tm.title_id
LEFT JOIN bonus_db.users_target_rank u
    ON non9.jmoa_code = u.jmoa_code
),


-- ランクアップ、初回購入情報
rank_up_add_non9_addTitle AS (
    SELECT
        non9.introducer_title_name as title_name,
        non9.introducer_code,
        non9.jmoa_code as jwoa_code,
        non9.send_bv_name as jwoa_name,
        rank_up.custom_bv,
        CASE
            WHEN non9.introducer_title_id >= 4
                THEN TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.20, 2)

            WHEN non9.introducer_title_id = 3
                THEN TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.15, 2)

            ELSE
                TRUNCATE(COALESCE(rank_up.custom_bv, 0) * 0.10, 2)
        END AS bonus_amount
    FROM rank_up_list AS rank_up
    LEFT JOIN user_introducer_non9_addTitle AS non9
      ON rank_up.distribution_jwoa_code = non9.jmoa_code
    where rank_up.custom_bv > 0
),






-- 条件を満たす紹介者（rank!=9 & bv>=50）が見つかるまで上へ辿る
chain_find AS (
    -- 1段目：最初に評価する紹介者 = u.introducer_code
    SELECT
        u.jmoa_code       AS jmoa_code,
        u.new_rank            AS jmoa_rank,
        u.introducer_code AS evaluated_code,
        1                 AS lvl,
        CASE
            WHEN up.new_rank <> 9 AND IFNULL(p.bv, 0) >= 50 THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM user_in_purchasers_list u
    LEFT JOIN bonus_db.users_target_rank up
      ON up.jmoa_code = u.introducer_code
    LEFT JOIN bonus_db.purchase_info_list p
      ON p.jwoa_code = up.jmoa_code
     AND p.year  = 2025
     AND p.month = 12

    UNION ALL

    -- 2段目以降
    SELECT
        c.jmoa_code,
        c.jmoa_rank,
        c.next_code       AS evaluated_code,
        c.lvl + 1         AS lvl,
        CASE
            WHEN up.new_rank <> 9 AND IFNULL(p.bv, 0) >= 50 THEN 1
            ELSE 0
        END AS found,
        up.introducer_code AS next_code
    FROM chain_find c
    JOIN bonus_db.users_target_rank up
      ON up.jmoa_code = c.next_code
    LEFT JOIN bonus_db.purchase_info_list p
      ON p.jwoa_code = up.jmoa_code
     AND p.year  = %s
     AND p.month = %s
    WHERE c.next_code IS NOT NULL
      AND c.found = 0
      AND c.lvl < 100
),

first_found AS (
    SELECT
        jmoa_code,
        MIN(lvl) AS hit_lvl
    FROM chain_find
    WHERE found = 1
    GROUP BY jmoa_code
),

-- 一般会員以外 & 前月再購入
user_introducer_non9_2 AS (
SELECT
    c.evaluated_code AS introducer_code,
    u.new_rank           AS introducer_rank,
    c.jmoa_code,
    c.jmoa_rank,
    p.bv             AS introducer_bv,
    c.lvl
FROM chain_find c
JOIN first_found f
  ON f.jmoa_code = c.jmoa_code
 AND f.hit_lvl   = c.lvl
JOIN bonus_db.users_target_rank u
  ON u.jmoa_code = c.evaluated_code
JOIN bonus_db.purchase_info_list p
  ON p.jwoa_code = c.evaluated_code
 AND p.year  = %s
 AND p.month = %s
WHERE c.found = 1
ORDER BY c.jmoa_code
),

-- non9_2にタイトルを追加
user_introducer_non9_2_addTitle AS (
SELECT
    non9.introducer_code,
    non9.introducer_rank,
    non9.jmoa_code,
    u.send_bv_name,
    non9.jmoa_rank,
    non9.lvl,
    tm.title_id as introducer_title_id,
    tm.title_name as introducer_title_name
FROM user_introducer_non9_2 AS non9
LEFT JOIN bonus_db.users_target_rank ui
    ON non9.introducer_code = ui.jmoa_code
LEFT JOIN bonus_db.user_titles ut
    ON ut.jmoa_code = ui.jmoa_code
LEFT JOIN bonus_db.title_master tm
    ON ut.title_id = tm.title_id
LEFT JOIN bonus_db.users_target_rank u
    ON non9.jmoa_code = u.jmoa_code
),

-- 再購入情報
repurchase_add_non9_2_addTitle AS (
    SELECT
        non9.introducer_title_name as title_name,
        non9.introducer_code,
        non9.jmoa_code as jwoa_code,
        non9.send_bv_name as jwoa_name,
        repurchase.custom_bv,
        CASE
            WHEN non9.introducer_title_id >= 4
                THEN TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.20, 2)

            WHEN non9.introducer_title_id = 3
                THEN TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.15, 2)

            ELSE
                TRUNCATE(COALESCE(repurchase.custom_bv, 0) * 0.10, 2)
        END AS bonus_amount
    FROM repurchase_list AS repurchase
    LEFT JOIN user_introducer_non9_2_addTitle AS non9
      ON repurchase.distribution_jwoa_code = non9.jmoa_code
    where repurchase.custom_bv > 0
),

pay_drive_list AS (
select * from rank_up_add_non9_addTitle
union all
select * from repurchase_add_non9_2_addTitle
)

select * from pay_drive_list order by introducer_code, jwoa_code
        """



        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [start_dt, end_dt, start_dt, end_dt, start_dt, end_dt, rank_dt, prev_year, prev_month, prev_year, prev_month])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # テンプレに渡す
        ctx["rows"] = rows
        return ctx




class TitleRegistrationView(generic.TemplateView):
    template_name = "title_registration.html"

    def _get_month_choices(self):
        today = date.today().replace(day=1)
        return [
            {
                "value": (today - relativedelta(months=i)).strftime("%Y-%m"),
                "year": (today - relativedelta(months=i)).year,
                "month": (today - relativedelta(months=i)).month,
            }
            for i in range(12)
        ]

    def _get_sql(self):
        sql = """
WITH orders AS (
    SELECT
        a.order_code,
        a.order_status,
        a.jwoa_code,
        a.deposit_at,
        b.jwoa_code AS jwoa_code1,
        b.distribution_bv
    FROM bonus_db.orders AS a
    LEFT JOIN bonus_db.orders_distribution_bv AS b
        ON a.order_code = b.order_code
    WHERE a.bv_actived_flg = 1
      AND a.deposit_at >= %s
      AND a.deposit_at < %s
      AND a.order_status <> 204
),

sum_bv AS (
    SELECT
        jwoa_code,
        jwoa_code1,
        SUM(IFNULL(distribution_bv, 0)) AS total_distribution_bv
    FROM orders
    GROUP BY jwoa_code, jwoa_code1
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY jwoa_code
            ORDER BY total_distribution_bv DESC
        ) AS rn
    FROM sum_bv
),

max_bv AS (
    SELECT
        jwoa_code,
        total_distribution_bv
    FROM ranked
    WHERE rn = 1
),

not_max_bv AS (
    SELECT
        jwoa_code,
        SUM(total_distribution_bv) AS income_bv
    FROM ranked
    WHERE rn <> 1
    GROUP BY jwoa_code
),

distinct_jwoa AS (
    SELECT DISTINCT
        jwoa_code
    FROM orders
),

bv_table AS (
    SELECT
        a.jwoa_code,
        IFNULL(max_bv.total_distribution_bv, 0) AS basic_bv,
        IFNULL(not_max_bv.income_bv, 0) AS income_bv
    FROM distinct_jwoa a
    LEFT JOIN max_bv
        ON a.jwoa_code = max_bv.jwoa_code
    LEFT JOIN not_max_bv
        ON a.jwoa_code = not_max_bv.jwoa_code
),

title_ranked AS (
    SELECT
        b.jwoa_code,
        b.basic_bv,
        b.income_bv,
        MAX(t.title_id) AS title_id,
        %s AS year,
        %s AS month
    FROM bv_table b
    LEFT JOIN bonus_db.title_master t
        ON b.basic_bv >= t.base_line
       AND b.income_bv >= t.income_line
    GROUP BY
        b.jwoa_code,
        b.basic_bv,
        b.income_bv
)

SELECT
    jwoa_code,
    basic_bv,
    income_bv,
    title_id,
    year,
    month
FROM title_ranked
WHERE title_id > 0
"""
        return sql

    def _fetch_rows(self, year, month):
        start = datetime(year, month, 1)
        end = start + relativedelta(months=1)

        sql = self._get_sql()
        params = [start, end, year, month]

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            print(cursor._executed)
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def _exists_data(self, year, month):
        sql = """
SELECT 1
FROM bonus_db.title_update_history
WHERE year = %s
  AND month = %s
LIMIT 1
        """
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [year, month])
            return cursor.fetchone() is not None

    def _insert_rows(self, year, month):
        start = datetime(year, month, 1)
        end = start + relativedelta(months=1)

        sql = f"""
INSERT INTO bonus_db.title_update_history
(
    jwoa_code,
    basic_bv,
    income_bv,
    title_id,
    year,
    month,
    created_at
)
SELECT
    t.jwoa_code,
    t.basic_bv,
    t.income_bv,
    t.title_id,
    t.year,
    t.month,
    CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
FROM (
{self._get_sql()}
) t
        """

        params = [start, end, year, month]

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)

    def _update_title(self, year, month):
        start = datetime(year, month, 1)
        end = start + relativedelta(months=1)

        sql = f"""
    UPDATE bonus_db.user_titles u
    JOIN (
    {self._get_sql()}
    ) t
      ON u.jmoa_code = t.jwoa_code
    SET
      u.title_id = t.title_id,
      u.update_date = CONVERT_TZ(NOW(), 'UTC', 'Asia/Tokyo')
    WHERE u.title_id <> t.title_id AND u.title_id < t.title_id
        """

        params = [start, end, year, month]

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)

    def _update_setting(self, year, month):
        value = f"{year}{month:02d}"

        sql = """
    UPDATE bonus_db.settings
    SET value = %s
    WHERE name = 'set_title'
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [value])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        month_choices = self._get_month_choices()
        selected = self.request.GET.get("target_month")

        ctx["month_choices"] = month_choices
        ctx["selected_month"] = selected
        ctx["rows"] = []

        if selected:
            try:
                y, m = map(int, selected.split("-"))
                ctx["rows"] = self._fetch_rows(y, m)
            except (ValueError, TypeError):
                ctx["rows"] = []

        return ctx

    def post(self, request, *args, **kwargs):
        selected = request.POST.get("target_month")

        if not selected:
            messages.error(request, "年月未選択です。")
            return redirect("connect:title_registration")

        try:
            y, m = map(int, selected.split("-"))
        except (ValueError, TypeError):
            messages.error(request, "年月の形式が不正です。")
            return redirect("connect:title_registration")

        # 事前チェック
        if self._exists_data(y, m):
            messages.warning(request, "すでに登録されています。")
            return redirect(f"{redirect('connect:title_registration').url}?target_month={selected}")

        try:
            with transaction.atomic(using="rds"):
                # タイトル更新履歴に登録
                self._insert_rows(y, m)

                # タイトルユーザーを更新
                self._update_title(y, m)

                # 設定を更新
                self._update_setting(y, m)

        except IntegrityError as e:
            print("IntegrityError:", e)
            traceback.print_exc()
            messages.warning(request, "すでに登録されています。")
            return redirect(f"{redirect('connect:title_registration').url}?target_month={selected}")

        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()
            messages.error(request, f"登録中にエラーが発生しました: {e}")
            return redirect(f"{redirect('connect:title_registration').url}?target_month={selected}")

        messages.success(request, "登録完了")
        return redirect(f"{redirect('connect:title_registration').url}?target_month={selected}")



class RepurchaseLastMonthView(generic.TemplateView):
    template_name = "repurchase_last_month.html"

    def _get_month_choices(self):
        today = date.today().replace(day=1)
        return [
            {
                "value": (today - relativedelta(months=i)).strftime("%Y-%m"),
                "year": (today - relativedelta(months=i)).year,
                "month": (today - relativedelta(months=i)).month,
            }
            for i in range(12)
        ]

    def _get_sql(self):
        return """
WITH bonus_orders AS (
    SELECT
        o.*,
        b.bonus_payment_date,
        COALESCE(b.bonus_payment_date, o.order_at) AS payment_date
    FROM bonus_db.orders AS o
    LEFT JOIN bonus_db.bonus_payment_date AS b
        ON o.order_code = b.order_code
),

aa as (
SELECT
    a.order_code,
    b.jwoa_code,
    u.send_bv_name,
    a.order_type,
    a.total_bv,
    b.distribution_bv AS bv,
    a.deposit_at,
    a.order_at,
    a.payment_date,
    %s AS year,
    %s AS month
FROM bonus_orders AS a
LEFT JOIN bonus_db.orders_distribution_bv AS b
    ON a.order_code = b.order_code
LEFT JOIN bonus_db.users AS u
    ON b.jwoa_code = u.jmoa_code
WHERE a.order_status NOT IN (206, 207, 208)
  AND a.payment_date >= %s
  AND a.payment_date < %s
  AND a.bv_actived_flg = 1

UNION ALL

SELECT
    doc_no AS order_code,
    member_no AS jwoa_code,
    firstname AS send_bv_name,
    105 AS order_type,
    0 AS total_bv,
    total_bv AS bv,
    payment_date AS deposit_at,
    payment_date AS order_at,
    payment_date AS bonus_payment_date,
    %s AS year,
    %s AS month
FROM bonus_db.api_users_bv
WHERE order_year = %s
  AND order_month = %s
)

SELECT *
FROM aa
"""

    def _fetch_rows(self, year, month):
        start = datetime(year, month, 1)
        end = start + relativedelta(months=1)

        sql = self._get_sql()
        params = [year, month, start, end, year, month, year, month]

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            print(cursor._executed)
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def _delete_rows(self, year, month):
        sql = """
DELETE FROM bonus_db.purchase_info_list
WHERE year = %s
  AND month = %s
"""
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [year, month])

    def _insert_rows(self, rows):
        insert_sql = """
INSERT INTO bonus_db.purchase_info_list
(
    year,
    month,
    jwoa_code,
    send_bv_name,
    order_code,
    total_bv,
    bv,
    order_type,
    deposit_at,
    order_at,
    bonus_payment_date
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

        data = [
            (
                r["year"],
                r["month"],
                r["jwoa_code"],
                r["send_bv_name"],
                r["order_code"],
                r["total_bv"],
                r["bv"],
                r["order_type"],
                r["deposit_at"],
                r["order_at"],
                r["payment_date"],
            )
            for r in rows
        ]

        with connections["rds"].cursor() as cursor:
            cursor.executemany(insert_sql, data)

    def _update_setting(self, year, month):
        value = f"{year}{month:02d}"

        sql = """
UPDATE bonus_db.settings
SET value = %s
WHERE name = 'set_title'
"""
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [value])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected = self.request.GET.get("target_month")
        ctx["month_choices"] = self._get_month_choices()
        ctx["selected_month"] = selected
        ctx["rows"] = []

        if selected:
            try:
                y, m = map(int, selected.split("-"))
                ctx["rows"] = self._fetch_rows(y, m)
            except (ValueError, TypeError):
                ctx["rows"] = []

        return ctx

    def post(self, request, *args, **kwargs):
        selected = request.POST.get("target_month")

        if not selected:
            messages.error(request, "年月未選択です。")
            return redirect("connect:repurchase_last_month")

        try:
            y, m = map(int, selected.split("-"))
        except (ValueError, TypeError):
            messages.error(request, "年月形式エラー")
            return redirect("connect:repurchase_last_month")

        rows = self._fetch_rows(y, m)
        if not rows:
            messages.info(request, "対象データなし")
            return redirect(
                f"{redirect('connect:repurchase_last_month').url}?target_month={selected}"
            )

        try:
            with transaction.atomic(using="rds"):
                self._delete_rows(y, m)
                self._insert_rows(rows)
                self._update_setting(y, m)

        except Exception as e:
            print(e)
            messages.error(request, f"エラー発生: {e}")
            return redirect(
                f"{redirect('connect:repurchase_last_month').url}?target_month={selected}"
            )

        messages.success(request, f"{len(rows)}件登録完了")
        return redirect(
            f"{redirect('connect:repurchase_last_month').url}?target_month={selected}"
        )


class RepurchaseExportView(RepurchaseListView):

    def get(self, request, *args, **kwargs):
        # 既存ロジック使う（これがポイント）
        ctx = self.get_context_data()

        rows = ctx["rows"]

        wb = Workbook()
        ws = wb.active
        ws.title = "購入情報"

        # ヘッダー
        headers = [
            "注文番号", "注文区分", "会員番号", "会員名",
            "total_bv", "bv", "BV反映日時", "注文日時",
            "ボーナス支払日", "作成日時"
        ]
        ws.append(headers)

        # データ
        for r in rows:
            order_type_map = {
                101: "再購入品",
                102: "初回購入品",
                103: "ランクアップ購入品",
                105: "特別対応購入品",
            }

            ws.append([
                r.get("order_code"),
                order_type_map.get(r.get("order_type"), r.get("order_type")),
                r.get("jwoa_code"),
                r.get("send_bv_name"),
                r.get("total_bv"),
                r.get("bv"),
                r.get("deposit_at"),
                r.get("order_at"),
                r.get("bonus_payment_date"),
                r.get("created_at"),
            ])

        # レスポンス
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="repurchase.xlsx"'

        wb.save(response)
        return response