from django.shortcuts import render
# Create your views here.

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

from django.db.models import Sum
from django.utils.timezone import make_aware
from .models import Plan, PlanDate, GenreList, Region, FavoritePlan

from .models import TitleMaster, PeriodMaster, UserTitles, Orders, User, PrevMonthPurchaseStatus


logger = logging.getLogger(__name__)


class IndexView(generic.ListView):
    template_name = "index.html"
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

        if selected_kibetu:
            period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()

            if period:
                ctx["selected_period"] = period

                st_date = period.st_date
                end_date = period.end_date

#                 table: orders
#                 group by: jwoa_code
#                 sum     :total_bv
                orders_summary = Orders.objects.using("rds").filter(
                    bv_actived_flg=True,
                    order_type__in=[102, 103],
                    bv_actived_at__date__range=(st_date, end_date)
                ).exclude(
                    order_status__in=[201, 202, 206]
                ).values(
                    "jwoa_code"
                ).annotate(
                    total_sum=Sum("total_bv")
                ).order_by(
                    "-total_sum"
                )

                # ★これが必要（テンプレに渡す）
                ctx["rows"] = orders_summary

        return ctx


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

        st_date = period.st_date
        end_date = period.end_date

        # 日付 -> datetime範囲（開始は00:00:00、終了は翌日00:00:00未満）
        start_dt = make_aware(datetime.combine(st_date, time.min))
        end_exclusive = make_aware(datetime.combine(end_date + timedelta(days=1), time.min))

        sql = """
SELECT
    a.introducer_code,
    a.jmoa_code,
    a.send_bv_name,
    a.title_id,
    a.title_name,
    bv.total_sum,

    CASE
        WHEN a.title_id >= 4
            THEN TRUNCATE(COALESCE(bv.total_sum, 0) * 0.20, 2)

        WHEN a.title_id = 3
            THEN TRUNCATE(COALESCE(bv.total_sum, 0) * 0.15, 2)

        ELSE
            TRUNCATE(COALESCE(bv.total_sum, 0) * 0.10, 2)
    END AS bonus_amount

FROM (
#アクティブ招待 + title
SELECT
    u.send_bv_name,
    copy_non9.*,
    tm.title_id,
    tm.title_name
FROM bonus_db.copy_introducer_non9 AS copy_non9
LEFT JOIN bonus_db.users ui
    ON copy_non9.introducer_code = ui.jmoa_code
LEFT JOIN bonus_db.user_titles ut
    ON ut.user_id = ui.id
LEFT JOIN bonus_db.title_master tm
    ON ut.title_id = tm.title_id
LEFT JOIN bonus_db.users u
    ON copy_non9.jmoa_code = u.jmoa_code

) AS a

LEFT JOIN (
    SELECT
        o.distribution_jwoa_code AS jwoa_code,
        SUM(o.custom_total_bv)   AS total_sum
    FROM (
        SELECT
            b.jwoa_code AS distribution_jwoa_code,
            a.bv_actived_flg,
            a.deposit_at,
            a.order_status,
            a.order_type,
            b.distribution_bv,

            CASE
                WHEN a.order_type = 101
                    THEN LEAST(IFNULL(b.distribution_bv, 0), 50)
                ELSE
                    IFNULL(b.distribution_bv, 0)
            END AS custom_total_bv
        FROM bonus_db.orders AS a
        LEFT JOIN bonus_db.orders_distribution_bv AS b
               ON a.order_code = b.order_code

        WHERE a.order_type IN (101, 102, 103)
 AND deposit_at >= %s
 AND deposit_at <  %s
        UNION ALL
        SELECT
            member_no AS distribution_jwoa_code,
            1         AS bv_actived_flg,
            payment_date as deposit_at,
            203       AS order_status,
            105       AS order_type,
            total_bv        AS distribution_bv,
            LEAST(IFNULL(total_bv, 0), 50) AS custom_total_bv

        FROM bonus_db.api_users_bv
    WHERE
        payment_date >= %s
        AND payment_date < %s
    ) AS o
    WHERE
        o.bv_actived_flg = 1
        AND o.order_status NOT IN (201, 202, 206)

    GROUP BY
        o.distribution_jwoa_code
) AS bv
    ON a.jmoa_code = bv.jwoa_code
WHERE
    bv.total_sum >= 1;
        """



        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [start_dt, end_exclusive, start_dt, end_exclusive])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # テンプレに渡す
        ctx["rows"] = rows
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

        if selected_kibetu:
            period = PeriodMaster.objects.using("rds").filter(kibetu=selected_kibetu).first()

            if period:
                ctx["selected_period"] = period

                st_date = period.st_date
                end_date = period.end_date

#                 table: orders
#                 group by: jwoa_code
#                 sum     :total_bv
                orders_summary = Orders.objects.using("rds").filter(
                    bv_actived_flg=True,
                    order_type__in=[102, 103],
                    bv_actived_at__date__range=(st_date, end_date)
                ).exclude(
                    order_status__in=[201, 202, 206]
                ).values(
                    "jwoa_code"
                ).annotate(
                    total_sum=Sum("total_bv")
                ).order_by(
                    "-total_sum"
                )

                # ★これが必要（テンプレに渡す）
                ctx["rows"] = orders_summary

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
    context_object_name = "object_list"
    model = PeriodMaster
    paginate_by = 10

    def get_queryset(self):
        return PeriodMaster.objects.using("rds").all()



class TitleListView(generic.ListView):
    template_name = "title_list.html"
    context_object_name = "object_list"
    model = TitleMaster

    def get_queryset(self):
        return TitleMaster.objects.using("rds").all()



class RepurchaseLastMonthView(generic.ListView):
    template_name = "repurchase_last_month.html"
    context_object_name = "object_list"
    model = PrevMonthPurchaseStatus

    def get_queryset(self):
        today = date.today()
        default_target = today.replace(day=1) - relativedelta(months=1)

        return (
            PrevMonthPurchaseStatus.objects
            .using("rds")
            .filter(create_status=0)
            .filter(
                Q(year__lt=default_target.year) |
                Q(year=default_target.year, month__lte=default_target.month)
            )
            .order_by("year", "month")
        )

    def _fetch_rows(self, year: int, month: int):
        base_date = datetime(year, month, 1, 0, 0, 0)
        next_month_start = base_date + relativedelta(months=1)

        sql = """
SELECT
    b.jwoa_code,
    users.send_bv_name,
    SUM(b.distribution_bv) AS total_bv,
    %s as year,
    %s as month
FROM bonus_db.orders AS a
LEFT JOIN bonus_db.orders_distribution_bv AS b
    ON a.order_code = b.order_code
LEFT JOIN users
    ON b.jwoa_code = users.jmoa_code
WHERE a.order_status NOT IN (201, 206)
  AND a.deposit_at >= %s
  AND a.deposit_at <  %s
GROUP BY b.jwoa_code
HAVING SUM(b.distribution_bv) >= 50;
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [year, month, base_date, next_month_start])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def post(self, request, *args, **kwargs):
        """✅ 登録ボタンで purchase_info_list に保存"""
        selected_prev_month = request.POST.get("prev_month")
        if not selected_prev_month:
            messages.error(request, "対象年月が未選択です。")
            return redirect("connect:repurchase_last_month")

        period = (
            PrevMonthPurchaseStatus.objects
            .using("rds")
            .filter(id=selected_prev_month)
            .first()
        )
        if not period:
            messages.error(request, "対象データが見つかりません。")
            return redirect("connect:repurchase_last_month")

        rows = self._fetch_rows(period.year, period.month)
        if not rows:
            messages.info(request, "登録対象データがありません（BV>=50 なし）。")
            return redirect(f"{redirect('connect:repurchase_last_month').url}?prev_month={selected_prev_month}")

        upsert_sql = """
INSERT INTO bonus_db.purchase_info_list
(year, month, jwoa_code, send_bv_name, bv)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  send_bv_name = VALUES(send_bv_name),
  bv = VALUES(bv),
  updated_at = CURRENT_TIMESTAMP;
        """

        data = [
            (r["year"], r["month"], r["jwoa_code"], r["send_bv_name"], int(r["total_bv"]))
            for r in rows
        ]

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                cursor.executemany(upsert_sql, data)

            # 任意：作成済みにする（一覧候補から除外される）
            period.create_status = 1
            period.save(using="rds", update_fields=["create_status"])

        messages.success(request, f"登録しました（{len(rows)}件）。")
        return redirect(f"{redirect('connect:repurchase_last_month').url}?prev_month={selected_prev_month}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_prev_month = self.request.GET.get("prev_month")
        ctx["selected_prev_month"] = selected_prev_month
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_prev_month:
            return ctx

        period = PrevMonthPurchaseStatus.objects.using("rds").filter(id=selected_prev_month).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        ctx["rows"] = self._fetch_rows(period.year, period.month)
        return ctx




class RepurchaseListView(generic.ListView):
    template_name = "repurchase_last_month.html"
    context_object_name = "object_list"
    model = PrevMonthPurchaseStatus

    def get_queryset(self):
        today = date.today()
        default_target = today.replace(day=1) - relativedelta(months=1)

        return (
            PrevMonthPurchaseStatus.objects
            .using("rds")
            .filter(create_status=0)
            .filter(
                Q(year__lt=default_target.year) |
                Q(year=default_target.year, month__lte=default_target.month)
            )
            .order_by("year", "month")
        )

    def _fetch_rows(self, year: int, month: int):
        base_date = datetime(year, month, 1, 0, 0, 0)
        next_month_start = base_date + relativedelta(months=1)

        sql = """
SELECT
    b.jwoa_code,
    users.send_bv_name,
    SUM(b.distribution_bv) AS total_bv,
    %s as year,
    %s as month
FROM bonus_db.orders AS a
LEFT JOIN bonus_db.orders_distribution_bv AS b
    ON a.order_code = b.order_code
LEFT JOIN users
    ON b.jwoa_code = users.jmoa_code
WHERE a.order_status NOT IN (201, 206)
  AND a.deposit_at >= %s
  AND a.deposit_at <  %s
GROUP BY b.jwoa_code
HAVING SUM(b.distribution_bv) >= 50;
        """

        with connections["rds"].cursor() as cursor:
            cursor.execute(sql, [year, month, base_date, next_month_start])
            logger.info(f"Executed SQL: {cursor._executed}")
            cols = [c[0] for c in cursor.description]
            return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def post(self, request, *args, **kwargs):
        """✅ 登録ボタンで purchase_info_list に保存"""
        selected_prev_month = request.POST.get("prev_month")
        if not selected_prev_month:
            messages.error(request, "対象年月が未選択です。")
            return redirect("connect:repurchase_last_month")

        period = (
            PrevMonthPurchaseStatus.objects
            .using("rds")
            .filter(id=selected_prev_month)
            .first()
        )
        if not period:
            messages.error(request, "対象データが見つかりません。")
            return redirect("connect:repurchase_last_month")

        rows = self._fetch_rows(period.year, period.month)
        if not rows:
            messages.info(request, "登録対象データがありません（BV>=50 なし）。")
            return redirect(f"{redirect('connect:repurchase_last_month').url}?prev_month={selected_prev_month}")

        upsert_sql = """
INSERT INTO bonus_db.purchase_info_list
(year, month, jwoa_code, send_bv_name, bv)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  send_bv_name = VALUES(send_bv_name),
  bv = VALUES(bv),
  updated_at = CURRENT_TIMESTAMP;
        """

        data = [
            (r["year"], r["month"], r["jwoa_code"], r["send_bv_name"], int(r["total_bv"]))
            for r in rows
        ]

        with transaction.atomic(using="rds"):
            with connections["rds"].cursor() as cursor:
                cursor.executemany(upsert_sql, data)

            # 任意：作成済みにする（一覧候補から除外される）
            period.create_status = 1
            period.save(using="rds", update_fields=["create_status"])

        messages.success(request, f"登録しました（{len(rows)}件）。")
        return redirect(f"{redirect('connect:repurchase_last_month').url}?prev_month={selected_prev_month}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        selected_prev_month = self.request.GET.get("prev_month")
        ctx["selected_prev_month"] = selected_prev_month
        ctx["rows"] = []
        ctx["selected_period"] = None

        if not selected_prev_month:
            return ctx

        period = PrevMonthPurchaseStatus.objects.using("rds").filter(id=selected_prev_month).first()
        if not period:
            return ctx

        ctx["selected_period"] = period
        ctx["rows"] = self._fetch_rows(period.year, period.month)
        return ctx