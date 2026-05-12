# crm/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('',                              views.dashboard,           name='dashboard'),
    path('leads/',                        views.lead_list,           name='lead_list'),
    path('leads/new/',                    views.lead_create,         name='lead_create'),
    path('leads/<int:pk>/',              views.lead_detail,         name='lead_detail'),
    path('leads/<int:pk>/status/',       views.lead_update_status,  name='lead_update_status'),
    path('leads/<int:lead_pk>/log/',     views.log_activity,        name='log_activity'),
    path('customers/',                   views.customer_list,       name='customer_list'),
    path('customers/<int:pk>/',          views.customer_detail,     name='customer_detail'),
    path('pipeline/',                    views.pipeline_board,      name='pipeline_board'),
    path('analytics/',                   views.sales_analytics,     name='sales_analytics'),
    path('analytics/json/',              views.analytics_json,      name='analytics_json'),
    path('dashboard-ui/',                views.lead_dashboard,      name='lead_dashboard'),
]
