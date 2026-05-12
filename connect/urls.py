from django.urls import path
from . import views



app_name = 'connect'
urlpatterns = [
    path('', views.IndexView.as_view(), name="index"),
    path("repurchase/export/", views.RepurchaseExportView.as_view(), name="repurchase_export"),
    path('kibetu/', views.KibetuView.as_view(), name = "kibetu"),
    path('title_list/', views.TitleListView.as_view(), name = "title_list"),
    path('title_user/', views.TitleUserView.as_view(), name = "title_user"),
    path('placement_tree/', views.PlacementTreeView.as_view(), name = "placement_tree"),
    path('settings/', views.SettingsView.as_view(), name = "settings"),
    path('repurchase_last_month/', views.RepurchaseLastMonthView.as_view(), name = "repurchase_last_month"),
    path('repurchase_list/', views.RepurchaseListView.as_view(), name = "repurchase_list"),
    path('inquiry/', views.InquiryView.as_view(), name = "inquiry"),
    path('plan-list/', views.PlanListView.as_view(), name="plan-list"),
    path('plan-detail/<int:pk>/', views.PlanDetailView.as_view(), name="plan-detail"),
    path('add_favorite_to_db/', views.AddFavoriteToDBView.as_view(), name="add_favorite_to_db"),
    path('user_target_rank/', views.UserTargetRankView.as_view(), name = "user_target_rank"),
    path('title_registration/', views.TitleRegistrationView.as_view(), name = "title_registration"),
    path("bonus_payment_date/", views.BonusPaymentDateView.as_view(), name="bonus_payment_date"),
    path("active_users/", views.ActiveUsersView.as_view(), name="active_users"),

    path('drive_bonus/', views.DriveBonusView.as_view(), name = "drive_bonus"),
    path('basic_bonus/', views.BasicBonusView.as_view(), name = "basic_bonus"),
    path('matching_bonus/', views.MatchingBonusView.as_view(), name = "matching_bonus"),
    path('title_bonus/', views.TitleBonusView.as_view(), name = "title_bonus"),

    path('s_drive_bonus/', views.S_DriveBonusView.as_view(), name = "s_drive_bonus"),
    path('s_basic_bonus/', views.S_BasicBonusView.as_view(), name = "s_basic_bonus"),
    path('s_matching_bonus/', views.S_MatchingBonusView.as_view(), name = "s_matching_bonus"),


]
