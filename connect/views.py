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
import openpyxl

from django.db.models import Sum
from django.utils.timezone import make_aware
from .models import Plan, PlanDate, GenreList, Region, FavoritePlan

from .models import TitleMaster, PeriodMaster, UserTitles, Orders, User, PurchaseInfoList
from .models import Settings

from connect.sql.drive_bonus_sql import DRIVE_BONUS_SQL
from connect.sql.basic_bonus_sql import BASIC_BONUS_SQL
from connect.sql.matching_bonus_sql import MATCHING_BONUS_SQL
from connect.sql.title_bonus_sql import TITLE_BONUS_SQL
from connect.sql.title_diff_bonus_sql import TITLE_DIFF_BONUS_SQL
from connect.sql.repurchase_over_bonus_sql import REPURCHASE_OVER_BONUS_SQL
from connect.sql.three_star_diamond_global_bonus_q_sql import THREE_STAR_DIAMOND_GLOBAL_BONUS_Q_SQL
from connect.sql.crown_diamond_global_bonus_y_sql import CROWN_DIAMOND_GLOBAL_BONUS_Y_SQL


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

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        selected_kibetu = request.POST.get("kibetu", "").strip()

        if action != "register_drive_bonus":
            messages.error(request, "不正な操作です。")
            return redirect("connect:drive_bonus")

        if not selected_kibetu:
            messages.error(request, "期別を選択してください。")
            return redirect("connect:drive_bonus")

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            messages.error(request, "選択された期別が存在しません。")
            return redirect("connect:drive_bonus")

        try:
            rows = self._get_drive_bonus_rows(selected_kibetu, period)

            if not rows:
                messages.warning(request, "登録対象データがありません。")
                return redirect(f"/drive_bonus/?kibetu={selected_kibetu}")

            insert_sql = """
                INSERT INTO bonus_db.B_drive_bonus_result (
                    kibetu,
                    title_name,
                    introducer_code,
                    jwoa_code,
                    jwoa_name,
                    sum_bv,
                    sum_bonus_amount,
                    created_at
                ) VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                ON DUPLICATE KEY UPDATE
                    title_name = VALUES(title_name),
                    introducer_code = VALUES(introducer_code),
                    jwoa_name = VALUES(jwoa_name),
                    sum_bv = VALUES(sum_bv),
                    sum_bonus_amount = VALUES(sum_bonus_amount),
                    created_at = NOW()
            """

            insert_params = []
            for r in rows:
                insert_params.append([
                    selected_kibetu,
                    r.get("title_name") or "",
                    r.get("introducer_code") or "",
                    r.get("jwoa_code") or "",
                    r.get("jwoa_name") or "",
                    r.get("sum_bv") or 0,
                    r.get("sum_bonus_amount") or 0,
                ])

            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.executemany(insert_sql, insert_params)

            messages.success(request, f"{len(rows)}件をドライブボーナス結果に登録しました。")

        except Exception as e:
            logger.exception("ドライブボーナス結果登録エラー")
            messages.error(request, f"登録中にエラーが発生しました: {e}")

        return redirect(f"/drive_bonus/?kibetu={selected_kibetu}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")
        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        ctx["rows"] = self._get_drive_bonus_rows(selected_kibetu, period)

        return ctx

    def _get_drive_bonus_rows(self, selected_kibetu, period):
        st_date = period.st_date
        end_date = period.end_date

        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])

        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_year = prev_month_last.year
        prev_month = prev_month_last.month

        be_start_dt = make_aware(datetime(prev_year, prev_month, 1, 0, 0, 0))
        be_end_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))


        params = [
            prev_year,
            prev_month,
            start_dt,
            end_dt,
            start_dt,
            end_dt,
            be_start_dt,
            be_end_dt,
            be_end_dt,
        ]

        with connections["rds"].cursor() as cursor:
            cursor.execute(DRIVE_BONUS_SQL, params)
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        return rows



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

    DEFAULT_PER_PAGE = 100
    MAX_PER_PAGE = 500

    def _build_where(
        self,
        year=None,
        month=None,
        q_code: str = "",
        q_name: str = "",
        q_order_code: str = "",
        q_order_type: str = "",
        q_bonus_date_from: str = "",
        q_bonus_date_to: str = "",
    ):
        where = ["1=1"]
        params = []

        if year is not None and month is not None:
            where.append("year = %s")
            where.append("month = %s")
            params.extend([year, month])

        if q_code:
            where.append("jwoa_code LIKE %s")
            params.append(f"%{q_code}%")

        if q_name:
            where.append("send_bv_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_order_code:
            where.append("order_code LIKE %s")
            params.append(f"%{q_order_code}%")

        if q_order_type:
            where.append("order_type = %s")
            params.append(q_order_type)

        if q_bonus_date_from:
            where.append("bonus_payment_date >= %s")
            params.append(q_bonus_date_from)

        if q_bonus_date_to:
            where.append("bonus_payment_date < DATE_ADD(%s, INTERVAL 1 DAY)")
            params.append(q_bonus_date_to)

        return "WHERE " + " AND ".join(where), params

    def _get_registered_months(self):
        sql = """
            SELECT DISTINCT CONCAT(year, '-', LPAD(month, 2, '0')) AS ym
            FROM bonus_db.purchase_info_list
            ORDER BY ym DESC
        """
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql)
            return [row[0] for row in cursor.fetchall()]

    def _fetch_rows(
        self,
        year=None,
        month=None,
        q_code: str = "",
        q_name: str = "",
        q_order_code: str = "",
        q_order_type: str = "",
        q_bonus_date_from: str = "",
        q_bonus_date_to: str = "",
        limit: int = 100,
        offset: int = 0,
    ):
        where_sql, params = self._build_where(
            year=year,
            month=month,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
            q_bonus_date_from=q_bonus_date_from,
            q_bonus_date_to=q_bonus_date_to,
        )

        sql = f"""
            SELECT
                order_code,
                order_type,
                jwoa_code,
                send_bv_name,
                total_bv,
                bv,
                deposit_at,
                order_at,
                bonus_payment_date,
                created_at,
                year,
                month
            FROM bonus_db.purchase_info_list
            {where_sql}
            ORDER BY bonus_payment_date DESC, id DESC
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def _count_rows(
        self,
        year=None,
        month=None,
        q_code: str = "",
        q_name: str = "",
        q_order_code: str = "",
        q_order_type: str = "",
        q_bonus_date_from: str = "",
        q_bonus_date_to: str = "",
    ) -> int:
        where_sql, params = self._build_where(
            year=year,
            month=month,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
            q_bonus_date_from=q_bonus_date_from,
            q_bonus_date_to=q_bonus_date_to,
        )

        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM bonus_db.purchase_info_list
            {where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_month = (self.request.GET.get("target_month") or "").strip()

        q_code = (self.request.GET.get("q_code") or "").strip()
        q_name = (self.request.GET.get("q_name") or "").strip()
        q_order_code = (self.request.GET.get("q_order_code") or "").strip()
        q_order_type = (self.request.GET.get("q_order_type") or "").strip()
        q_bonus_date_from = (self.request.GET.get("q_bonus_date_from") or "").strip()
        q_bonus_date_to = (self.request.GET.get("q_bonus_date_to") or "").strip()

        try:
            per_page = int(self.request.GET.get("per_page") or str(self.DEFAULT_PER_PAGE))
        except ValueError:
            per_page = self.DEFAULT_PER_PAGE

        per_page = max(1, min(per_page, self.MAX_PER_PAGE))

        try:
            page = int(self.request.GET.get("page") or "1")
        except ValueError:
            page = 1

        page = max(1, page)

        ctx["month_choices"] = self._get_month_choices()
        ctx["registered_months"] = self._get_registered_months()

        ctx["selected_month"] = selected_month
        ctx["q_code"] = q_code
        ctx["q_name"] = q_name
        ctx["q_order_code"] = q_order_code
        ctx["q_order_type"] = q_order_type
        ctx["q_bonus_date_from"] = q_bonus_date_from
        ctx["q_bonus_date_to"] = q_bonus_date_to
        ctx["per_page"] = per_page

        year = None
        month = None
        ctx["selected_period"] = None

        if selected_month:
            try:
                year, month = map(int, selected_month.split("-"))
                ctx["selected_period"] = {
                    "year": year,
                    "month": month,
                }
            except ValueError:
                year = None
                month = None

        total_count = self._count_rows(
            year=year,
            month=month,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
            q_bonus_date_from=q_bonus_date_from,
            q_bonus_date_to=q_bonus_date_to,
        )

        total_pages = max(1, math.ceil(total_count / per_page))

        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page

        rows = self._fetch_rows(
            year=year,
            month=month,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
            q_bonus_date_from=q_bonus_date_from,
            q_bonus_date_to=q_bonus_date_to,
            limit=per_page,
            offset=offset,
        )

        base_params = {}

        if selected_month:
            base_params["target_month"] = selected_month
        if q_code:
            base_params["q_code"] = q_code
        if q_name:
            base_params["q_name"] = q_name
        if q_order_code:
            base_params["q_order_code"] = q_order_code
        if q_order_type:
            base_params["q_order_type"] = q_order_type
        if q_bonus_date_from:
            base_params["q_bonus_date_from"] = q_bonus_date_from
        if q_bonus_date_to:
            base_params["q_bonus_date_to"] = q_bonus_date_to
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        ctx["rows"] = rows
        ctx["total_count"] = total_count
        ctx["page"] = page
        ctx["total_pages"] = total_pages
        ctx["has_prev"] = page > 1
        ctx["has_next"] = page < total_pages
        ctx["prev_page"] = page - 1
        ctx["next_page"] = page + 1
        ctx["base_qs"] = urlencode(base_params)

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

    DEFAULT_PER_PAGE = 10
    MAX_PER_PAGE = 500

    # ----------------------------
    # UI: 月リスト
    # ----------------------------
    def get_month_list(self):
        today = date.today().replace(day=1)
        months = []
        for i in range(0, 13):
            d = today - relativedelta(months=i)
            months.append({
                "value": f"{d.year}-{d.month:02d}",
                "year": d.year,
                "month": d.month,
            })
        return months

    def _month_end_exclusive(self, year: int, month: int):
        base = datetime(year, month, 1, 0, 0, 0)
        return base + relativedelta(months=1)

    # ----------------------------
    # WHERE句
    # ----------------------------
    def _build_where(self, q_code: str = "", q_name: str = "", q_new_rank: str = ""):
        where = ["1=1"]
        params = []

        if q_code:
            where.append("t.jmoa_code LIKE %s")
            params.append(f"%{q_code}%")

        if q_name:
            where.append("t.send_bv_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_new_rank:
            where.append("""
CASE
  WHEN t.status_code <> 1 THEN 9
  WHEN x.fluctuation_name REGEXP '^[0-9]+$' THEN CAST(x.fluctuation_name AS UNSIGNED)
  ELSE t.`rank`
END = %s
""")
            params.append(q_new_rank)

        where_sql = "WHERE " + " AND ".join(where)
        return where_sql, params

    # ----------------------------
    # 総件数
    # ----------------------------
    def _fetch_total_count(self, cutoff_dt: datetime, q_code: str = "", q_name: str = "", q_new_rank: str = "") -> int:
        where_sql, params = self._build_where(q_code=q_code, q_name=q_name, q_new_rank=q_new_rank)

        sql = f"""
SELECT COUNT(*)
FROM bonus_db.users t
LEFT JOIN (
  SELECT user_id, fluctuation_name, created_at
  FROM (
    SELECT
      user_id,
      fluctuation_name,
      created_at,
      id,
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
{where_sql}
"""
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [cutoff_dt] + params)
            return int(cursor.fetchone()[0])

    # ----------------------------
    # 表示用データ
    # ----------------------------
    def _fetch_users(
        self,
        cutoff_dt: datetime,
        q_code: str = "",
        q_name: str = "",
        q_new_rank: str = "",
        limit: int = 100,
        offset: int = 0,
    ):
        where_sql, params = self._build_where(q_code=q_code, q_name=q_name, q_new_rank=q_new_rank)

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
      id,
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
{where_sql}
ORDER BY t.jmoa_code
LIMIT %s OFFSET %s
"""
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [cutoff_dt] + params + [limit, offset])
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    # ----------------------------
    # settings 取得
    # ----------------------------
    def _get_select_month_setting(self):
        with connections["rds"].cursor() as cursor:
            cursor.execute("""
                SELECT value
                FROM bonus_db.settings
                WHERE name = 'user_add_rank'
                LIMIT 1
            """)
            row = cursor.fetchone()
        return row[0] if row else ""

    # ----------------------------
    # GET
    # ----------------------------
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_prev_month = (self.request.GET.get("prev_month") or "").strip()
        q_code = (self.request.GET.get("q_code") or "").strip()
        q_name = (self.request.GET.get("q_name") or "").strip()
        q_new_rank = (self.request.GET.get("q_new_rank") or "").strip()

        per_page = 10

        try:
            page = int(self.request.GET.get("page") or "1")
        except ValueError:
            page = 1
        page = max(1, page)

        ctx["month_list"] = self.get_month_list()
        ctx["selected_prev_month"] = selected_prev_month
        ctx["selected_period"] = None
        ctx["columns"] = self.DISPLAY_COLUMNS
        ctx["rows"] = []
        ctx["total_count"] = 0
        ctx["select_month"] = self._get_select_month_setting()

        ctx["q_code"] = q_code
        ctx["q_name"] = q_name
        ctx["q_new_rank"] = q_new_rank
        ctx["per_page"] = per_page
        ctx["page"] = 1
        ctx["total_pages"] = 1
        ctx["has_prev"] = False
        ctx["has_next"] = False
        ctx["prev_page"] = 1
        ctx["next_page"] = 1
        ctx["base_qs"] = ""

        if not selected_prev_month:
            return ctx

        try:
            y, m = map(int, selected_prev_month.split("-"))
        except ValueError:
            return ctx

        ctx["selected_period"] = {"year": y, "month": m}
        cutoff_dt = self._month_end_exclusive(y, m)

        total_count = self._fetch_total_count(
            cutoff_dt=cutoff_dt,
            q_code=q_code,
            q_name=q_name,
            q_new_rank=q_new_rank,
        )

        total_pages = max(1, math.ceil(total_count / per_page))
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page

        rows = self._fetch_users(
            cutoff_dt=cutoff_dt,
            q_code=q_code,
            q_name=q_name,
            q_new_rank=q_new_rank,
            limit=per_page,
            offset=offset,
        )

        base_params = {
            "prev_month": selected_prev_month,
        }
        if q_code:
            base_params["q_code"] = q_code
        if q_name:
            base_params["q_name"] = q_name
        if q_new_rank:
            base_params["q_new_rank"] = q_new_rank
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        ctx["rows"] = rows
        ctx["total_count"] = total_count
        ctx["page"] = page
        ctx["total_pages"] = total_pages
        ctx["has_prev"] = page > 1
        ctx["has_next"] = page < total_pages
        ctx["prev_page"] = page - 1
        ctx["next_page"] = page + 1
        ctx["base_qs"] = urlencode(base_params)

        return ctx

    # ----------------------------
    # POST: 登録（全件）
    # ----------------------------
    def post(self, request, *args, **kwargs):
        selected_prev_month = (request.POST.get("prev_month") or "").strip()
        if not selected_prev_month:
            messages.error(request, "対象年月が未選択です。")
            return redirect("connect:user_target_rank")

        year, month = map(int, selected_prev_month.split("-"))
        cutoff_dt = self._month_end_exclusive(year, month)
        target_rank = f"{year}{month:02d}"

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
      id,
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
            cursor.execute("TRUNCATE TABLE bonus_db.users_target_rank")
            cursor.execute(insert_sql, [cutoff_dt])
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

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        selected_kibetu = request.POST.get("kibetu", "").strip()

        if action != "register_basic_bonus":
            messages.error(request, "不正な操作です。")
            return redirect("connect:basic_bonus")

        if not selected_kibetu:
            messages.error(request, "期別を選択してください。")
            return redirect("connect:basic_bonus")

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            messages.error(request, "選択された期別が存在しません。")
            return redirect("connect:basic_bonus")

        try:
            rows = self._get_basic_bonus_rows(selected_kibetu, period)

            if not rows:
                messages.warning(request, "登録対象データがありません。")
                return redirect(f"/basic_bonus/?kibetu={selected_kibetu}")

            insert_sql = """
                INSERT INTO bonus_db.B_basic_bonus_result (
                    kibetu,
                    placement_code,
                    placement_name,
                    placement_rank,
                    line_code,
                    purchaser_code,
                    purchaser_name,
                    level,
                    sum_bv,
                    plus_carry_bv,
                    bonus_rate,
                    bonus_amount,
                    blue_daiya_flg,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON DUPLICATE KEY UPDATE
                    placement_name = VALUES(placement_name),
                    placement_rank = VALUES(placement_rank),
                    purchaser_name = VALUES(purchaser_name),
                    level = VALUES(level),
                    sum_bv = VALUES(sum_bv),
                    plus_carry_bv = VALUES(plus_carry_bv),
                    bonus_rate = VALUES(bonus_rate),
                    bonus_amount = VALUES(bonus_amount),
                    blue_daiya_flg = VALUES(blue_daiya_flg),
                    created_at = NOW()
            """

            insert_params = []
            for r in rows:
                insert_params.append([
                    selected_kibetu,
                    r.get("placement_code") or "",
                    r.get("placement_name") or "",
                    r.get("placement_rank") or 0,
                    r.get("line_code") or "",
                    r.get("purchaser_code") or "",
                    r.get("purchaser_name") or "",
                    r.get("level") or 0,
                    r.get("sum_bv") or 0,
                    r.get("plus_carry_bv") or 0,
                    r.get("bonus_rate") or 0,
                    r.get("bonus_amount") or 0,
                    r.get("blue_daiya_flg") or 0,
                ])

            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.executemany(insert_sql, insert_params)

            messages.success(request, f"{len(rows)}件をベーシックボーナス結果に登録しました。")

        except Exception as e:
            logger.exception("ベーシックボーナス結果登録エラー")
            messages.error(request, f"登録中にエラーが発生しました: {e}")

        return redirect(f"/basic_bonus/?kibetu={selected_kibetu}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")
        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        ctx["rows"] = self._get_basic_bonus_rows(selected_kibetu, period)

        return ctx

    def _get_basic_bonus_rows(self, selected_kibetu, period):
        st_date = period.st_date
        end_date = period.end_date

        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])

        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_year = prev_month_last.year
        prev_month = prev_month_last.month

        be_start_dt = make_aware(datetime(prev_year, prev_month, 1, 0, 0, 0))
        be_end_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))


        params = [
            prev_year,
            prev_month,
            selected_kibetu,
            be_start_dt,
            be_end_dt,
            start_dt,
            end_dt,
            start_dt,
            end_dt,
        ]

        with connections["rds"].cursor() as cursor:
            cursor.execute(BASIC_BONUS_SQL, params)
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        return rows




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

    def _get_registered_months(self):
        sql = """
        SELECT DISTINCT CONCAT(year, '-', LPAD(month,2,'0')) AS ym
        FROM bonus_db.purchase_info_list
        """
        with connections["rds"].cursor() as cursor:
            cursor.execute(sql)
            return [row[0] for row in cursor.fetchall()]

    def _get_sql(self):
        return """
WITH bonus_orders AS (
    SELECT
        o.*,
        b.bonus_payment_date,
        COALESCE(b.bonus_payment_date, o.deposit_at) AS payment_date
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
        ctx["registered_months"] = self._get_registered_months()
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

    def get(self, request):
        view = RepurchaseListView()

        selected_month = (request.GET.get("prev_month") or "").strip()
        q_code = (request.GET.get("q_code") or "").strip()
        q_name = (request.GET.get("q_name") or "").strip()
        q_order_code = (request.GET.get("q_order_code") or "").strip()
        q_order_type = (request.GET.get("q_order_type") or "").strip()
        q_bonus_date_from = (request.GET.get("q_bonus_date_from") or "").strip()
        q_bonus_date_to = (request.GET.get("q_bonus_date_to") or "").strip()

        year, month = None, None
        if selected_month:
            try:
                year, month = map(int, selected_month.split("-"))
            except:
                pass

        # 🔥 ここがポイント（limitなし）
        rows = view._fetch_rows(
            year=year,
            month=month,
            q_code=q_code,
            q_name=q_name,
            q_order_code=q_order_code,
            q_order_type=q_order_type,
            q_bonus_date_from=q_bonus_date_from,
            q_bonus_date_to=q_bonus_date_to,
            limit=1000000,   # or LIMIT外す専用関数でもOK
            offset=0
        )

        # Excel出力処理（例）
        wb = openpyxl.Workbook()
        ws = wb.active

        ws.append([
            "注文番号","注文区分","会員番号","会員名",
            "total_bv","bv","BV反映日時","注文日時","ボーナス支払日","作成日時"
        ])

        for r in rows:
            ws.append([
                r["order_code"],
                r["order_type"],
                r["jwoa_code"],
                r["send_bv_name"],
                r["total_bv"],
                r["bv"],
                r["deposit_at"],
                r["order_at"],
                r["bonus_payment_date"],
                r["created_at"],
            ])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=repurchase.xlsx'

        wb.save(response)
        return response



class BonusPaymentDateView(generic.TemplateView):
    template_name = "bonus_payment_date.html"

    def _fetch_rows(self, q_order_code: str = ""):
        sql = """
SELECT
    order_code,
    bonus_payment_date,
    created_at
FROM bonus_db.bonus_payment_date
WHERE 1=1
"""
        params = []

        if q_order_code:
            sql += "  AND order_code LIKE %s\n"
            params.append(f"%{q_order_code}%")

        sql += """
ORDER BY created_at DESC, order_code ASC
LIMIT 2000
"""

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_order_code = (self.request.GET.get("q_order_code") or "").strip()

        ctx["q_order_code"] = q_order_code
        ctx["rows"] = self._fetch_rows(q_order_code=q_order_code)

        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        order_code = (request.POST.get("order_code") or "").strip()
        bonus_payment_date = (request.POST.get("bonus_payment_date") or "").strip()

        q_order_code = (request.POST.get("q_order_code") or "").strip()
        redirect_path = f"/bonus_payment_date/?q_order_code={q_order_code}"

        if action == "create":
            if not order_code:
                messages.error(request, "注文番号を入力してください。")
                return redirect("connect:bonus_payment_date")

            insert_sql = """
            INSERT INTO bonus_db.bonus_payment_date (
                order_code,
                bonus_payment_date
            ) VALUES (%s, %s)
            """

            update_sql = """
            UPDATE bonus_db.purchase_info_list
            SET
                bonus_payment_date = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_code = %s
            """

            try:
                with transaction.atomic(using="rds"):
                    with connections["rds"].cursor() as cursor:
                        cursor.execute(insert_sql, [order_code, bonus_payment_date or None])
                        cursor.execute(update_sql, [bonus_payment_date or None, order_code])

                messages.success(request, "登録しました。")
            except Exception as e:
                messages.error(request, f"登録に失敗しました: {e}")

            return redirect(redirect_path)

        elif action == "update":
            if not order_code:
                messages.error(request, "注文番号が不正です。")
                return redirect(redirect_path)

            sql1 = """
            UPDATE bonus_db.bonus_payment_date
            SET bonus_payment_date = %s
            WHERE order_code = %s
            """

            sql2 = """
            UPDATE bonus_db.purchase_info_list
            SET
                bonus_payment_date = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_code = %s
            """

            try:
                with transaction.atomic(using="rds"):
                    with connections["rds"].cursor() as cursor:
                        cursor.execute(sql1, [bonus_payment_date or None, order_code])
                        cursor.execute(sql2, [bonus_payment_date or None, order_code])

                messages.success(request, "更新しました。")
            except Exception as e:
                messages.error(request, f"更新に失敗しました: {e}")

            return redirect(redirect_path)

        elif action == "delete":
            if not order_code:
                messages.error(request, "注文番号が不正です。")
                return redirect(redirect_path)

            sql = """
            DELETE FROM bonus_db.bonus_payment_date
            WHERE order_code = %s
            """

            try:
                with connections["rds"].cursor() as cursor:
                    cursor.execute(sql, [order_code])
                messages.success(request, "削除しました。")
            except Exception as e:
                messages.error(request, f"削除に失敗しました: {e}")

            return redirect(redirect_path)

        messages.error(request, "不正な操作です。")
        return redirect(redirect_path)


class ActiveUsersView(generic.TemplateView):
    template_name = "active_users.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_jwoa_code = self.request.GET.get("q_jwoa_code", "").strip()
        q_year = self.request.GET.get("q_year", "").strip()
        q_month = self.request.GET.get("q_month", "").strip()

        ctx["q_jwoa_code"] = q_jwoa_code
        ctx["q_year"] = q_year
        ctx["q_month"] = q_month
        ctx["rows"] = []

        where_clauses = []
        params = []

        if q_jwoa_code:
            where_clauses.append("a.jwoa_code LIKE %s")
            params.append(f"%{q_jwoa_code}%")

        if q_year:
            where_clauses.append("a.year = %s")
            params.append(int(q_year))

        if q_month:
            where_clauses.append("a.month = %s")
            params.append(int(q_month))

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
            SELECT
                a.id,
                a.jwoa_code,
                a.year,
                a.month,
                a.created_at,
                u.send_bv_name
            FROM active_users a
            LEFT JOIN users u
                ON a.jwoa_code = u.jmoa_code
            {where_sql}
            ORDER BY a.jwoa_code, a.year DESC, a.month DESC
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            ctx["rows"] = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")

        q_jwoa_code = request.POST.get("q_jwoa_code", "").strip()
        q_year = request.POST.get("q_year", "").strip()
        q_month = request.POST.get("q_month", "").strip()

        if action == "create":
            return self._create(request, q_jwoa_code, q_year, q_month)

        if action == "update":
            return self._update(request, q_jwoa_code, q_year, q_month)

        if action == "delete":
            return self._delete(request, q_jwoa_code, q_year, q_month)

        messages.error(request, "不正な操作です。")
        return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

    def _create(self, request, q_jwoa_code, q_year, q_month):
        jwoa_code = request.POST.get("jwoa_code", "").strip()
        year = request.POST.get("year", "").strip()
        month = request.POST.get("month", "").strip()

        error_message = self._validate_input(jwoa_code, year, month)
        if error_message:
            messages.error(request, error_message)
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        sql = """
            INSERT INTO active_users (
                jwoa_code,
                year,
                month,
                created_at
            ) VALUES (
                %s,
                %s,
                %s,
                NOW()
            )
        """

        try:
            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.execute(sql, [jwoa_code, int(year), int(month)])

            messages.success(request, "登録しました。")

        except IntegrityError as e:
            error_text = str(e)

            if "uq_active_users_jwoa_year_month" in error_text or "Duplicate entry" in error_text:
                messages.error(request, "この会員コード・年・月のデータはすでに登録されています。")
            else:
                messages.error(request, "登録に失敗しました。会員コードが存在しない可能性があります。")

        except Exception as e:
            messages.error(request, f"登録中にエラーが発生しました: {e}")

        return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

    def _update(self, request, q_jwoa_code, q_year, q_month):
        row_id = request.POST.get("id", "").strip()
        jwoa_code = request.POST.get("jwoa_code", "").strip()
        year = request.POST.get("year", "").strip()
        month = request.POST.get("month", "").strip()

        if not row_id:
            messages.error(request, "更新対象IDがありません。")
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        try:
            row_id_int = int(row_id)
        except ValueError:
            messages.error(request, "更新対象IDが不正です。")
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        error_message = self._validate_input(jwoa_code, year, month)
        if error_message:
            messages.error(request, error_message)
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        sql = """
            UPDATE active_users
            SET
                jwoa_code = %s,
                year = %s,
                month = %s
            WHERE id = %s
        """

        try:
            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.execute(sql, [jwoa_code, int(year), int(month), row_id_int])

            messages.success(request, "更新しました。")

        except IntegrityError as e:
            error_text = str(e)

            if "uq_active_users_jwoa_year_month" in error_text or "Duplicate entry" in error_text:
                messages.error(request, "この会員コード・年・月のデータはすでに登録されています。")
            else:
                messages.error(request, "更新に失敗しました。会員コードが存在しない可能性があります。")

        except Exception as e:
            messages.error(request, f"更新中にエラーが発生しました: {e}")

        return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

    def _delete(self, request, q_jwoa_code, q_year, q_month):
        row_id = request.POST.get("id", "").strip()

        if not row_id:
            messages.error(request, "削除対象IDがありません。")
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        try:
            row_id_int = int(row_id)
        except ValueError:
            messages.error(request, "削除対象IDが不正です。")
            return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

        sql = """
            DELETE FROM active_users
            WHERE id = %s
        """

        try:
            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.execute(sql, [row_id_int])

            messages.success(request, "削除しました。")

        except Exception as e:
            messages.error(request, f"削除中にエラーが発生しました: {e}")

        return redirect(self._get_redirect_url(q_jwoa_code, q_year, q_month))

    def _validate_input(self, jwoa_code, year, month):
        if not jwoa_code:
            return "会員コードを入力してください。"

        if not year:
            return "年を入力してください。"

        if not month:
            return "月を入力してください。"

        try:
            year_int = int(year)
        except ValueError:
            return "年は数値で入力してください。"

        try:
            month_int = int(month)
        except ValueError:
            return "月は数値で入力してください。"

        if year_int < 1900 or year_int > 2100:
            return "年は 1900〜2100 の範囲で入力してください。"

        if month_int < 1 or month_int > 12:
            return "月は 1〜12 の範囲で入力してください。"

        return None

    def _get_redirect_url(self, q_jwoa_code, q_year, q_month):
        base_url = "/active_users/"

        query_params = {}

        if q_jwoa_code:
            query_params["q_jwoa_code"] = q_jwoa_code

        if q_year:
            query_params["q_year"] = q_year

        if q_month:
            query_params["q_month"] = q_month

        if query_params:
            return base_url + "?" + urlencode(query_params)

        return base_url



class PlacementTreeView(generic.TemplateView):
    template_name = "placement_tree.html"

    DEFAULT_PER_PAGE = 200
    MAX_PER_PAGE = 500

    def _build_where(self, q_jwoa_code: str, q_name: str, q_placement_code: str):
        where = []
        params = []

        if q_jwoa_code:
            where.append("c.jwoa_code LIKE %s")
            params.append(f"%{q_jwoa_code}%")

        if q_name:
            where.append("c.send_bv_name LIKE %s")
            params.append(f"%{q_name}%")

        if q_placement_code:
            where.append("c.placement_code LIKE %s")
            params.append(f"%{q_placement_code}%")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        return where_sql, params

    def _fetch_total_count(self, q_jwoa_code: str, q_name: str, q_placement_code: str) -> int:
        where_sql, params = self._build_where(q_jwoa_code, q_name, q_placement_code)

        sql = f"""
SELECT COUNT(*)
FROM bonus_db.C_users_placement_tree_cache c
{where_sql}
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.fetchone()[0])

    def _fetch_rows_keyset(
        self,
        q_jwoa_code: str,
        q_name: str,
        q_placement_code: str,
        limit: int,
        after_id: str = "",
    ):
        where_sql, params = self._build_where(q_jwoa_code, q_name, q_placement_code)

        keyset_sql = ""
        if after_id:
            if where_sql:
                keyset_sql = " AND c.id > %s"
            else:
                keyset_sql = "WHERE c.id > %s"
            params.append(after_id)

        sql = f"""
SELECT
    c.id,
    c.placement_code,
    c.placement_name,
    c.placement_rank,
    c.jwoa_code,
    c.send_bv_name,
    c.new_rank,
    c.tree_level,
    c.created_at
FROM bonus_db.C_users_placement_tree_cache c
{where_sql}
{keyset_sql}
ORDER BY c.id
LIMIT %s
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, params + [limit])
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _copy_from_view(self) -> int:
        delete_sql = "DELETE FROM bonus_db.C_users_placement_tree_cache"

        insert_sql = """
INSERT INTO bonus_db.C_users_placement_tree_cache (
    placement_code,
    placement_name,
    placement_rank,
    jwoa_code,
    send_bv_name,
    new_rank,
    tree_level
)
SELECT
    placement_code,
    placement_name,
    placement_rank,
    jmoa_code,
    send_bv_name,
    new_rank,
    tree_level
FROM bonus_db.v_user_placement_tree
        """

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                cursor.execute(delete_sql)
                cursor.execute(insert_sql)
                inserted_count = cursor.rowcount

        return inserted_count

    def _delete_all_cache(self) -> int:
        sql = "DELETE FROM bonus_db.C_users_placement_tree_cache"

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                cursor.execute(sql)
                deleted_count = cursor.rowcount

        return deleted_count

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()

        try:
            if action == "copy":
                inserted_count = self._copy_from_view()
                messages.success(
                    request,
                    f"上位者ツリーテーブル へ {inserted_count} 件コピー登録しました。"
                )
            elif action == "delete":
                deleted_count = self._delete_all_cache()
                messages.success(
                    request,
                    f"上位者ツリーテーブルを全件削除しました。"
                )
            else:
                messages.warning(request, "不正な操作です。")
        except Exception as e:
            messages.error(request, f"処理中にエラーが発生しました: {e}")

        return redirect("connect:placement_tree")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        q_jwoa_code = (self.request.GET.get("q_jwoa_code") or "").strip()
        q_name = (self.request.GET.get("q_name") or "").strip()
        q_placement_code = (self.request.GET.get("q_placement_code") or "").strip()

        try:
            per_page = int(self.request.GET.get("per_page") or str(self.DEFAULT_PER_PAGE))
        except ValueError:
            per_page = self.DEFAULT_PER_PAGE
        per_page = max(1, min(per_page, self.MAX_PER_PAGE))

        after_id = (self.request.GET.get("after_id") or "").strip()

        total_count = self._fetch_total_count(q_jwoa_code, q_name, q_placement_code)
        total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1

        rows = self._fetch_rows_keyset(
            q_jwoa_code=q_jwoa_code,
            q_name=q_name,
            q_placement_code=q_placement_code,
            limit=per_page,
            after_id=after_id,
        )

        next_after_id = ""
        if rows:
            next_after_id = str(rows[-1]["id"])

        base_params = {}
        if q_jwoa_code:
            base_params["q_jwoa_code"] = q_jwoa_code
        if q_name:
            base_params["q_name"] = q_name
        if q_placement_code:
            base_params["q_placement_code"] = q_placement_code
        if per_page != self.DEFAULT_PER_PAGE:
            base_params["per_page"] = per_page

        current_page = 1
        if after_id:
            req_page = self.request.GET.get("page")
            try:
                current_page = max(1, int(req_page)) if req_page else 2
            except ValueError:
                current_page = 2

        ctx["rows"] = rows
        ctx["total_count"] = total_count
        ctx["per_page"] = per_page

        ctx["q_jwoa_code"] = q_jwoa_code
        ctx["q_name"] = q_name
        ctx["q_placement_code"] = q_placement_code

        ctx["page"] = current_page
        ctx["total_pages"] = total_pages
        ctx["base_qs"] = urlencode(base_params)

        ctx["has_next"] = (
            len(rows) == per_page
            and bool(next_after_id)
        )
        ctx["next_after_id"] = next_after_id
        ctx["has_prev_hint"] = bool(after_id)

        return ctx



class MatchingBonusView(generic.ListView):
    template_name = "matching_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster


    def get_queryset(self):
        return PeriodMaster.objects.using("rds").all()

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        return self.render_to_response(context)


    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        selected_kibetu = request.POST.get("kibetu", "").strip()

        if action != "register_basic_bonus":
            messages.error(request, "不正な操作です。")
            return redirect("connect:matching_bonus")

        if not selected_kibetu:
            messages.error(request, "期別を選択してください。")
            return redirect("connect:matching_bonus")

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            messages.error(request, "選択された期別が存在しません。")
            return redirect("connect:matching_bonus")

        try:
            rows = self._get_basic_bonus_rows(selected_kibetu, period)

            if not rows:
                messages.warning(request, "登録対象データがありません。")
                return redirect(f"/matching_bonus/?kibetu={selected_kibetu}")

            insert_sql = """
                INSERT INTO bonus_db.B_matching_bonus_result (
                    kibetu,
                    introducer_code,
                    introducer_name,
                    active_count,
                    basic_bv,
                    matching_bv,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, NOW()
                )
                ON DUPLICATE KEY UPDATE
                    introducer_name = VALUES(introducer_name),
                    active_count    = VALUES(active_count),
                    basic_bv        = VALUES(basic_bv),
                    matching_bv     = VALUES(matching_bv),
                    created_at      = NOW()
            """

            insert_params = []
            for r in rows:
                insert_params.append([
                    selected_kibetu,
                    r.get("introducer_code") or "",
                    r.get("jwoa_name") or "",
                    r.get("active_count") or 0,
                    r.get("sum_bonus_amount") or 0,
                    r.get("matching_bonus_amount") or 0,
                ])

            with transaction.atomic(using="rds"):
                with connections["rds"].cursor() as cursor:
                    cursor.executemany(insert_sql, insert_params)

            messages.success(request, f"{len(rows)}件をマッチングボーナス結果に登録しました。")

        except Exception as e:
            logger.exception("マッチングボーナス結果登録エラー")
            messages.error(request, f"登録中にエラーが発生しました: {e}")

        return redirect(f"/basic_bonus/?kibetu={selected_kibetu}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")
        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        ctx["rows"] = self._get_basic_bonus_rows(selected_kibetu, period)

        return ctx

    def _get_basic_bonus_rows(self, selected_kibetu, period):
        st_date = period.st_date
        end_date = period.end_date

        kibetu_year = int(selected_kibetu[0:4])
        kibetu_month = int(selected_kibetu[5:7])

        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_dt = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        current_month_first = datetime(kibetu_year, kibetu_month, 1)
        prev_month_last = current_month_first - timedelta(days=1)

        prev_year = prev_month_last.year
        prev_month = prev_month_last.month

        be_start_dt = make_aware(datetime(prev_year, prev_month, 1, 0, 0, 0))
        be_end_dt = make_aware(datetime(kibetu_year, kibetu_month, 1, 0, 0, 0))


        params = [
            be_start_dt,
            be_end_dt,
            selected_kibetu,
        ]

        with connections["rds"].cursor() as cursor:
            cursor.execute(MATCHING_BONUS_SQL, params)
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        return rows




class S_DriveBonusView(generic.ListView):
    template_name = "s_drive_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster

    def get_queryset(self):
        # B_drive_bonus_result に登録済みの期別だけ取得
        with connections["rds"].cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT kibetu
                FROM bonus_db.B_drive_bonus_result
                ORDER BY kibetu
            """)
            registered_kibetu_list = [row[0] for row in cursor.fetchall()]

        if not registered_kibetu_list:
            return PeriodMaster.objects.using("rds").none()

        return (
            PeriodMaster.objects.using("rds")
            .filter(kibetu__in=registered_kibetu_list)
            .order_by("kibetu")
        )

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        if request.GET.get("export") == "excel":
            rows = context.get("rows", [])

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "DriveBonusResult"

            headers = ["タイトル", "紹介者ID", "会員ID", "会員名", "BV合計", "報酬"]
            ws.append(headers)

            for r in rows:
                ws.append([
                    r.get("title_name"),
                    r.get("introducer_code"),
                    r.get("jwoa_code"),
                    r.get("jwoa_name"),
                    r.get("sum_bv"),
                    r.get("sum_bonus_amount"),
                ])

            ws.column_dimensions["A"].width = 18
            ws.column_dimensions["B"].width = 15
            ws.column_dimensions["C"].width = 15
            ws.column_dimensions["D"].width = 25
            ws.column_dimensions["E"].width = 12
            ws.column_dimensions["F"].width = 15

            for row_idx in range(2, ws.max_row + 1):
                ws[f"E{row_idx}"].number_format = '#,##0'
                ws[f"F{row_idx}"].number_format = '#,##0.00'

            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="drive_bonus_result.xlsx"'

            wb.save(response)
            return response

        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")

        # 期別未選択なら、登録済み期別の先頭を自動選択
        if not selected_kibetu and self.object_list:
            selected_kibetu = self.object_list[0].kibetu

        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period

        sql = """
            SELECT
                id,
                kibetu,
                title_name,
                introducer_code,
                jwoa_code,
                jwoa_name,
                sum_bv,
                sum_bonus_amount,
                created_at
            FROM bonus_db.B_drive_bonus_result
            WHERE kibetu = %s
            ORDER BY introducer_code, jwoa_code
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [selected_kibetu])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        ctx["rows"] = rows

        return ctx




class S_BasicBonusView(generic.ListView):
    template_name = "s_basic_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster

    def get_queryset(self):
        # B_drive_bonus_result に登録済みの期別だけ取得
        with connections["rds"].cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT kibetu
                FROM bonus_db.B_drive_bonus_result
                ORDER BY kibetu
            """)
            registered_kibetu_list = [row[0] for row in cursor.fetchall()]

        if not registered_kibetu_list:
            return PeriodMaster.objects.using("rds").none()

        return (
            PeriodMaster.objects.using("rds")
            .filter(kibetu__in=registered_kibetu_list)
            .order_by("kibetu")
        )

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        if request.GET.get("export") == "excel":
            rows = context.get("rows", [])

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "DriveBonusResult"

            headers = ["タイトル", "紹介者ID", "会員ID", "会員名", "BV合計", "報酬"]
            ws.append(headers)

            for r in rows:
                ws.append([
                    r.get("title_name"),
                    r.get("introducer_code"),
                    r.get("jwoa_code"),
                    r.get("jwoa_name"),
                    r.get("sum_bv"),
                    r.get("sum_bonus_amount"),
                ])

            ws.column_dimensions["A"].width = 18
            ws.column_dimensions["B"].width = 15
            ws.column_dimensions["C"].width = 15
            ws.column_dimensions["D"].width = 25
            ws.column_dimensions["E"].width = 12
            ws.column_dimensions["F"].width = 15

            for row_idx in range(2, ws.max_row + 1):
                ws[f"E{row_idx}"].number_format = '#,##0'
                ws[f"F{row_idx}"].number_format = '#,##0.00'

            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="drive_bonus_result.xlsx"'

            wb.save(response)
            return response

        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")

        # 期別未選択なら、登録済み期別の先頭を自動選択
        if not selected_kibetu and self.object_list:
            selected_kibetu = self.object_list[0].kibetu

        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period

        sql = """
            SELECT
                id,
                kibetu,
                title_name,
                introducer_code,
                jwoa_code,
                jwoa_name,
                sum_bv,
                sum_bonus_amount,
                created_at
            FROM bonus_db.B_drive_bonus_result
            WHERE kibetu = %s
            ORDER BY introducer_code, jwoa_code
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [selected_kibetu])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        ctx["rows"] = rows

        return ctx




class S_MatchingBonusView(generic.ListView):
    template_name = "s_matching_bonus.html"
    context_object_name = "object_list"
    model = PeriodMaster

    def get_queryset(self):
        # B_drive_bonus_result に登録済みの期別だけ取得
        with connections["rds"].cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT kibetu
                FROM bonus_db.B_matching_bonus_result
                ORDER BY kibetu
            """)
            registered_kibetu_list = [row[0] for row in cursor.fetchall()]

        if not registered_kibetu_list:
            return PeriodMaster.objects.using("rds").none()

        return (
            PeriodMaster.objects.using("rds")
            .filter(kibetu__in=registered_kibetu_list)
            .order_by("kibetu")
        )

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        if request.GET.get("export") == "excel":
            rows = context.get("rows", [])

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "MatchingBonusResult"

            headers = ["kibetu", "introducer_code", "introducer_name", "active_count", "basic_bv", "matching_bv", "created_at"]
            ws.append(headers)

            for r in rows:
                ws.append([
                    r.get("kibetu"),
                    r.get("introducer_code"),
                    r.get("introducer_name"),
                    r.get("active_count"),
                    r.get("basic_bv"),
                    r.get("matching_bv"),
                    r.get("created_at"),
                ])

            ws.column_dimensions["A"].width = 18
            ws.column_dimensions["B"].width = 15
            ws.column_dimensions["C"].width = 15
            ws.column_dimensions["D"].width = 25
            ws.column_dimensions["E"].width = 12
            ws.column_dimensions["F"].width = 15

            for row_idx in range(2, ws.max_row + 1):
                ws[f"E{row_idx}"].number_format = '#,##0'
                ws[f"F{row_idx}"].number_format = '#,##0.00'

            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="matching_bonus_result.xlsx"'

            wb.save(response)
            return response

        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_kibetu = self.request.GET.get("kibetu")

        # 期別未選択なら、登録済み期別の先頭を自動選択
        if not selected_kibetu and self.object_list:
            selected_kibetu = self.object_list[0].kibetu

        ctx["selected_kibetu"] = selected_kibetu
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_kibetu:
            return ctx

        period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()
        if not period:
            return ctx

        ctx["selected_period"] = period

        sql = """
            SELECT
                id,
                kibetu,
                introducer_code,
                introducer_name,
                active_count,
                basic_bv,
                matching_bv,
                created_at
            FROM bonus_db.B_matching_bonus_result
            WHERE kibetu = %s
            ORDER BY introducer_code
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [selected_kibetu])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        ctx["rows"] = rows

        return ctx