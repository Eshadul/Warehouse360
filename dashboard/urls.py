from django.urls import path
from . import views

urlpatterns = [
    # --- Auth ---
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # --- Main Nav ---
    path('', views.dashboard_view, name='dashboard'),
    
    path('asin-upc/', views.asin_upc_view, name='asin_upc'),
    # Note: We renamed this view function and URL name
    path('order-fulfillment/', views.order_fulfillment_view, name='order_fulfillment'), 
    
    # --- Store (Create/Update) ---
    path('store-management/', views.store_management_view, name='store_management'),
    path('store/update/<int:pk>/', views.store_management_view, name='store_update'),
    
    # --- User (Create/Update) ---
    path('create-user/', views.create_user_view, name='create_user'),
    path('user/update/<int:pk>/', views.create_user_view, name='user_update'), # <-- NEWLY ADDED
    
    # --- Warehouse (Create/Update) ---
    path('create-warehouse/', views.create_warehouse_view, name='create_warehouse'),
    path('warehouse/update/<int:pk>/', views.create_warehouse_view, name='warehouse_update'),
    
    # --- Dashboard Cards ---
    path('delivered-to-warehouse/', views.delivered_to_warehouse_view, name='delivered_to_warehouse'),
    path('out-of-stock/', views.out_of_stock_view, name='out_of_stock'),
    path('ready-to-ship/', views.ready_to_ship_view, name='ready_to_ship'),
    path('total-shipment/', views.total_shipment_view, name='total_shipment'),
]