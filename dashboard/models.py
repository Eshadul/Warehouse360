from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

# ---------------------------------
# CORE MODELS
# ---------------------------------

class Warehouse(models.Model):
    """
    Model for physical warehouse locations.
    Super Admin creates this.
    """
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Store(models.Model):
    """
    Model for sales channels (e.g., Amazon, Walmart).
    Linked to a specific Warehouse.
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stores')
    store_name = models.CharField(max_length=100)
    store_type = models.CharField(max_length=50, blank=True) # e.g., "Amazon", "Walmart"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.store_name} ({self.warehouse.name})"

# ---------------------------------
# USER AND ROLE MODELS
# ---------------------------------

class Role(models.Model):
    """
    Defines the roles available in the system (e.g., Super Admin, Store Manager).
    This allows for more flexible role management.
    """
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('warehouse_admin', 'Warehouse Admin'),
        ('store_manager', 'Store Manager'),
        ('warehouse_manager', 'Warehouse Manager'),
    ]
    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()

class User(AbstractUser):
    """
    Custom User Model.
    Contains a 'primary_role' for main permission checks,
    and a ManyToManyField for specific warehouse assignments.
    """
    # --- THIS IS THE CRITICAL FIX ---
    # We re-add a 'primary_role' field. This determines the user's
    # main identity for sidebar visibility and edit permissions.
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('warehouse_admin', 'Warehouse Admin'),
        ('store_manager', 'Store Manager'),
        ('warehouse_manager', 'Warehouse Manager'),
    ]
    primary_role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='store_manager',
        help_text="The main role for permission checks."
    )
    # --- END CRITICAL FIX ---

    full_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    
    # This links User to Warehouse/Role combinations
    warehouses = models.ManyToManyField(
        Warehouse, 
        through='UserWarehouseRole', 
        related_name='users'
    )

    def __str__(self):
        return self.username

class UserWarehouseRole(models.Model):
    """
    Intermediate model (linking table) for Many-to-Many relationship.
    Links a User to a specific Role at a specific Warehouse.
    e.g., 'Amit' (User) is 'Warehouse Admin' (Role) at 'Dhaka' (Warehouse).
    e.g., 'Amit' (User) is 'Store Manager' (Role) at 'Dhaka' (Warehouse).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'warehouse', 'role') # Ensures no duplicate entries

    def __str__(self):
        return f"{self.user.username} - {self.warehouse.name} ({self.role.name})"


# ---------------------------------
# PRODUCT AND FULFILLMENT MODELS
# ---------------------------------

class Product(models.Model):
    """
    Model for ASIN/UPC product master data.
    """
    code = models.CharField(max_length=100, unique=True, help_text="ASIN or UPC code")
    product_name = models.CharField(max_length=255)
    code_type = models.CharField(max_length=10, choices=[('asin', 'ASIN'), ('upc', 'UPC')])
    product_image_link = models.URLField(blank=True, null=True)
    minimum_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product_name} ({self.code})"

class OrderFulfillment(models.Model):
    """
    Model for the 'Supplier To Warehouse' form (Order Fulfillment).
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('delivered', 'Delivered to Warehouse'),
        ('out_of_stock', 'Out of Stock'),
    ]

    store = models.ForeignKey(Store, on_delete=models.SET_NULL, null=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True) # Linked via ASIN/UPC
    
    # Form Fields
    code_type = models.CharField(max_length=50, blank=True)
    team_code = models.CharField(max_length=50, blank=True)
    supplier_order_id = models.CharField(max_length=100, blank=True)
    quantity = models.IntegerField(default=1)
    amazon_order_id = models.CharField(max_length=100, blank=True)
    shipping_label_url = models.URLField(blank=True, null=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    tracker_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    # Status (for Warehouse Manager)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    action_taken_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='actioned_orders')
    action_taken_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Order {self.id} for {self.product.product_name if self.product else 'N/A'}"