from django.urls import path
from . import views

urlpatterns = [
    # --- Auth ---
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # --- Role Selection ---
    path('select-role/', views.select_role_view, name='select_role'),
    path('set-active-role/<int:assignment_id>/', views.set_active_role, name='set_active_role'),

    # --- Main Nav ---
    path('', views.dashboard_view, name='dashboard'),
    
    # --- ASIN/UPC (Product) ---
    path('asin-upc/', views.asin_upc_view, name='asin_upc'),
    path('product/update/<int:pk>/', views.asin_upc_view, name='product_update'),
    
    # --- Order Fulfillment ---
    path('order-fulfillment/', views.order_fulfillment_view, name='order_fulfillment'), 
    path('order-fulfillment/update/<int:pk>/', views.order_fulfillment_view, name='order_fulfillment_update'), 
    path('order-fulfillment/action/<int:pk>/<str:action_type>/', views.order_fulfillment_action, name='order_fulfillment_action'), 
    path('order-fulfillment/action/rts/<int:pk>/', views.rts_action_view, name='rts_action'), 
    path('order-fulfillment/action/ofs-to-dtw/<int:pk>/', views.ofs_to_dtw_action_view, name='ofs_to_dtw_action'), 
    
    # --- NEW CS ACTION URL ---
    path('order-fulfillment/action/cs/<int:pk>/', views.cs_action_view, name='cs_action'), # <-- NEW

    # --- Store (Create/Update) ---
    path('store-management/', views.store_management_view, name='store_management'),
    path('store/update/<int:pk>/', views.store_management_view, name='store_update'),
    
    # --- User (Create/Update) ---
    path('create-user/', views.create_user_view, name='create_user'),
    path('user/update/<int:pk>/', views.create_user_view, name='user_update'), 
    path('user/assignment/delete/<int:pk>/', views.delete_user_assignment, name='delete_user_assignment'),

    # --- Warehouse (Create/Update) ---
    path('create-warehouse/', views.create_warehouse_view, name='create_warehouse'),
    path('warehouse/update/<int:pk>/', views.create_warehouse_view, name='warehouse_update'),
    
    # --- Dashboard Cards ---
    path('delivered-to-warehouse/', views.delivered_to_warehouse_view, name='delivered_to_warehouse'),
    path('out-of-stock/', views.out_of_stock_view, name='out_of_stock'),
    path('ready-to-ship/', views.ready_to_ship_view, name='ready_to_ship'),
    path('total-shipment/', views.total_shipment_view, name='total_shipment'),

    # delete button---
    path('user/delete/<int:pk>/', views.delete_user_view, name='user_delete'),
    path('store/delete/<int:pk>/', views.delete_store_view, name='store_delete'),
    path('warehouse/delete/<int:pk>/', views.delete_warehouse_view, name='warehouse_delete'),

    # store name
    path('ajax/load-stores/', views.load_stores_ajax, name='ajax_load_stores'),
]
