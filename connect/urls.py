from django.urls import path
from . import views
from .business_carry_over_performance import CarryOverPerformanceView
from .business_team_performance import (
    BusinessTeamMonthPerformanceView,
    BusinessTeamWeekPerformanceView,
)



app_name = 'connect'
urlpatterns = [
    path('', views.IndexView.as_view(), name="index"),
    path("repurchase/export/", views.RepurchaseExportView.as_view(), name="repurchase_export"),
    path('kibetu/', views.KibetuView.as_view(), name = "kibetu"),
    path('kibetu_month/', views.KibetuMonthView.as_view(), name = "kibetu_month"),
    path('title_list/', views.TitleListView.as_view(), name = "title_list"),
    path('placement_tree/', views.PlacementTreeView.as_view(), name = "placement_tree"),
    path('settings/', views.SettingsView.as_view(), name = "settings"),
    path('repurchase_last_month/', views.RepurchaseLastMonthView.as_view(), name = "repurchase_last_month"),
    path('repurchase_list/', views.RepurchaseListView.as_view(), name = "repurchase_list"),
    path('inquiry/', views.InquiryView.as_view(), name = "inquiry"),
    path('user_target_rank/', views.UserTargetRankView.as_view(), name = "user_target_rank"),
    path('title_registration/', views.TitleRegistrationView.as_view(), name = "title_registration"),
    path("bonus_payment_date/", views.BonusPaymentDateView.as_view(), name="bonus_payment_date"),
    path("bonus_payment_date/template/", views.BonusPaymentDateTemplateView.as_view(), name="bonus_payment_date_template"),
    path("active_users/", views.ActiveUsersView.as_view(), name="active_users"),
    path("cooling_off/", views.CoolingOffView.as_view(), name="cooling_off"),

    path('users/', views.UsersView.as_view(), name = "users"),
    path('title_user/', views.TitleUserView.as_view(), name = "title_user"),
    path(
        "business_personal_performance/",
        views.BusinessPersonalMonthPerformanceView.as_view(),
        name="business_personal_performance",
    ),
    path(
        "business_team_performance/",
        BusinessTeamMonthPerformanceView.as_view(),
        name="business_team_performance",
    ),
    path(
        "business_personal_week_performance/",
        views.BusinessPersonalWeekPerformanceView.as_view(),
        name="business_personal_week_performance",
    ),
    path(
        "business_team_week_performance/",
        BusinessTeamWeekPerformanceView.as_view(),
        name="business_team_week_performance",
    ),
    path(
        "business_carry_over_performance/",
        CarryOverPerformanceView.as_view(),
        name="business_carry_over_performance",
    ),

    path('orders/', views.OrdersView.as_view(), name = "orders"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    path('orders_distribution_bv/', views.OrdersDistributionBvView.as_view(), name = "orders_distribution_bv"),
    path("api_users_bv/", views.ApiUsersBvView.as_view(), name="api_users_bv"),

    path('drive_bonus/', views.DriveBonusView.as_view(), name = "drive_bonus"),
    path('basic_bonus/', views.BasicBonusView.as_view(), name = "basic_bonus"),
    path('matching_bonus/', views.MatchingBonusView.as_view(), name = "matching_bonus"),
    path('title_bonus/', views.TitleBonusView.as_view(), name = "title_bonus"),
    path('title_diff_bonus/', views.TitleDiffBonusView.as_view(), name = "title_diff_bonus"),
    path('repurchase_over_bonus/', views.RepurchaseOverBonusView.as_view(), name = "repurchase_over_bonus"),
    path('three_star_global_bonus/', views.ThreeStarGlobalBonusView.as_view(), name = "three_star_global_bonus"),

    path('week_bonus/', views.WeekBonusView.as_view(), name = "week_bonus"),
    path('month_title/', views.MonthTitleView.as_view(), name = "month_title"),
    path('month_bonus/', views.MonthBonusView.as_view(), name = "month_bonus"),
    path("help_text/", views.BonusHelpTextView.as_view(), name="help_text"),
    path('bonus_histry/', views.BonusHistryView.as_view(), name = "bonus_histry"),
    path('bonus_histry_month/', views.BonusHistryMonthView.as_view(), name = "bonus_histry_month"),

    path('s_drive_bonus/', views.S_DriveBonusView.as_view(), name = "s_drive_bonus"),
    path('s_basic_bonus/', views.S_BasicBonusView.as_view(), name = "s_basic_bonus"),
    path('s_matching_bonus/', views.S_MatchingBonusView.as_view(), name = "s_matching_bonus"),
    path('s_month_title/', views.S_MonthTitleView.as_view(), name = "s_month_title"),
    path('s_title_bonus/', views.S_TitleBonusView.as_view(), name = "s_title_bonus"),
    path('s_title_diff_bonus/', views.S_TitleDiffBonusView.as_view(), name = "s_title_diff_bonus"),
    path('s_repurchase_over_bonus/', views.S_RepurchaseOverBonusView.as_view(), name = "s_repurchase_over_bonus"),
    path('s_three_star_global_bonus/', views.S_ThreeStarGlobalBonusView.as_view(), name = "s_three_star_global_bonus"),

    path('s_week_bonus/', views.S_WeekBonusView.as_view(), name = "s_week_bonus"),
    path('s_month_bonus/', views.S_MonthBonusView.as_view(), name = "s_month_bonus"),

]
