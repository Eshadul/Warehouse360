from django.contrib import admin
from .models import User, Warehouse, Store, Role, Product, OrderFulfillment, UserWarehouseRole

# Register your models here so you can see them in the admin panel.

# We can use this to show the M2M links directly on the User's admin page
class UserWarehouseRoleInline(admin.TabularInline):
    model = UserWarehouseRole
    extra = 1 # Show one extra blank slot

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'full_name', 'primary_role', 'is_staff')
    search_fields = ('username', 'full_name', 'email')
    list_filter = ('primary_role', 'is_active', 'is_staff')
    inlines = [UserWarehouseRoleInline] # Add the inline view

class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'created_at')
    search_fields = ('name',)

class StoreAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'warehouse', 'store_type', 'is_active')
    search_fields = ('store_name', 'warehouse__name')
    list_filter = ('is_active', 'store_type', 'warehouse')

class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_name_display')
    
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'code', 'code_type', 'minimum_price')
    search_fields = ('product_name', 'code')
    list_filter = ('code_type',)

class OrderFulfillmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'store', 'quantity', 'status', 'created_at')
    search_fields = ('product__product_name', 'store__store_name', 'amazon_order_id')
    list_filter = ('status', 'store', 'expected_delivery_date')

# Register all models
admin.site.register(User, UserAdmin)
admin.site.register(Warehouse, WarehouseAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(Role, RoleAdmin) # <-- This is the important one
admin.site.register(Product, ProductAdmin)
admin.site.register(OrderFulfillment, OrderFulfillmentAdmin)
admin.site.register(UserWarehouseRole)

