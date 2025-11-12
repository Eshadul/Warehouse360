from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard_view, name='dashboard'),
    path('total-shipment/', views.total_shipment_view, name='total_shipment'),
    path('supplier-to-warehouse/', views.supplier_to_warehouse, name='supplier_to_warehouse'),
    path('asin-upc/', views.asin_upc_view, name='asin_upc'),
    path('create-user/', views.create_user_view, name='create_user'),
    path('store_management/',views.store_management_view, name='store_management'),
    path('ready-to-ship/',views.ready_to_ship, name='ready_to_ship'),
    path('create-warehouse/',views.create_warehouse_view, name='create_warehouse'),
]
