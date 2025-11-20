from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Warehouse, Store, User, Role, UserWarehouseRole, Product, OrderFulfillment
from django.db import transaction
from django.core.exceptions import ValidationError

# --- Warehouse Form ---
class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'location']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
        }

# --- Store Form ---
class StoreForm(forms.ModelForm):
    STATUS_CHOICES = [
        (True, 'Active'),
        (False, 'Inactive'),
    ]
    is_active = forms.ChoiceField(
        choices=STATUS_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    class Meta:
        model = Store
        fields = ['warehouse', 'store_name', 'store_type', 'is_active']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'store_name': forms.TextInput(attrs={'class': 'form-control'}),
            'store_type': forms.TextInput(attrs={'class': 'form-control'}),
        }

# --- User Create Form (FIXED PASSWORD HASHING) ---
class UserCreateForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    primary_role = forms.ChoiceField(
        choices=User.ROLE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    profile_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            'username',
            'full_name',
            'email',
            'phone_number',
            'primary_role',
            'profile_image',
        )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        self.fields['password1'].label = "Password"
        self.fields['password2'].label = "Confirm Password"

        if self.user and self.user.primary_role == 'super_admin':
            self.fields['primary_role'].choices = User.ROLE_CHOICES
        elif self.user and self.user.primary_role == 'warehouse_admin':
            self.fields['primary_role'].choices = [
                ('store_manager', 'Store Manager'),
                ('warehouse_manager', 'Warehouse Manager'),
            ]

    def save(self, commit=True):
        # ✅ This calls UserCreationForm.save(),
        # which hashes password1 into user.password
        user = super().save(commit=False)

        # Add extra fields
        user.full_name = self.cleaned_data.get('full_name', '')
        user.email = self.cleaned_data.get('email', '')
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.primary_role = self.cleaned_data.get('primary_role')

        profile_image = self.cleaned_data.get('profile_image')
        if profile_image:
            user.profile_image = profile_image

        if commit:
            user.save()
        return user

    # === END FIX ===

# --- User Update Form ---
class UserUpdateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        required=False, 
        help_text="Leave blank to keep the current password."
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        required=False, 
        label="Confirm New Password"
    )
    # New profile image field
    profile_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'phone_number', 'primary_role', 'is_active', 'profile_image']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'primary_role': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

        if self.user and self.user.primary_role == 'super_admin':
             self.fields['primary_role'].choices = User.ROLE_CHOICES
        elif self.user and self.user.primary_role == 'warehouse_admin':
            self.fields['primary_role'].choices = [
                ('store_manager', 'Store Manager'),
                ('warehouse_manager', 'Warehouse Manager'),
            ]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password2 = cleaned_data.get("password2")

        if password and password != password2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password) 
        
        if commit:
            user.save()
        return user

# --- User Assignment Form ---
class UserAssignmentForm(forms.ModelForm):
    class Meta:
        model = UserWarehouseRole
        fields = ['warehouse', 'role', 'store']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select', 'id': 'id_warehouse'}),
            'role': forms.Select(attrs={'class': 'form-select', 'id': 'id_role'}),
            'store': forms.Select(attrs={'class': 'form-select', 'id': 'id_store'}),
        }

    def __init__(self, *args, **kwargs):
        # 1. EXTRACT CUSTOM ARGUMENTS FIRST
        # We must pop these BEFORE calling super(), otherwise Django throws the TypeError
        self.user = kwargs.pop('user', None)
        self.active_assignment = kwargs.pop('active_assignment', None)

        # 2. INITIALIZE STANDARD FORM
        super().__init__(*args, **kwargs)

        # 3. PERMISSION LOGIC (Filter Roles & Warehouses)
        is_warehouse_admin = False
        if self.user:
             if getattr(self.user, 'primary_role', '') == 'warehouse_admin':
                 is_warehouse_admin = True
             elif self.active_assignment and getattr(self.active_assignment.role, 'name', '') == 'warehouse_admin':
                 is_warehouse_admin = True

        if is_warehouse_admin:
            # Warehouse Admin: Can only assign Managers
            self.fields['role'].queryset = Role.objects.filter(
                name__in=['store_manager', 'warehouse_manager']
            )
            # Warehouse Admin: Can only assign to their CURRENT warehouse
            if self.active_assignment and self.active_assignment.warehouse:
                self.fields['warehouse'].queryset = Warehouse.objects.filter(
                    id=self.active_assignment.warehouse.id
                )
                self.fields['warehouse'].initial = self.active_assignment.warehouse
        else:
            # Super Admin: Can assign anything
            self.fields['role'].queryset = Role.objects.all()
            self.fields['warehouse'].queryset = Warehouse.objects.all()

        # 4. DYNAMIC STORE LOGIC
        # By default, empty the store dropdown
        self.fields['store'].queryset = Store.objects.none()

        # If form is bound (POST data)
        if 'warehouse' in self.data:
            try:
                warehouse_id = int(self.data.get('warehouse'))
                self.fields['store'].queryset = Store.objects.filter(warehouse_id=warehouse_id).order_by('store_name')
            except (ValueError, TypeError):
                pass  # invalid input
        # If editing an existing instance
        elif self.instance.pk and self.instance.warehouse:
            self.fields['store'].queryset = Store.objects.filter(warehouse=self.instance.warehouse).order_by('store_name')

# --- Product (ASIN/UPC) Form ---
# forms.py

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['code', 'product_name', 'code_type', 'product_image_link']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Code'}),
            'product_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product Name'}),
            'code_type': forms.Select(attrs={'class': 'form-select'}),
            'product_image_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Product Image Link'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # --- FIX: Custom Label for ChoiceField ---
        # empty_label doesn't work here. We must manually set the first choice.
        
        # 1. Get existing choices (excluding any default blank ones)
        choices = [c for c in self.fields['code_type'].choices if c[0] != '']
        
        # 2. Add our custom blank option at the top
        choices.insert(0, ('', 'Select ASIN/UPC'))
        
        # 3. Assign back to the field
        self.fields['code_type'].choices = choices
# --- Order Fulfillment Form ---
class OrderFulfillmentForm(forms.ModelForm):
    store = forms.ModelChoiceField(
        queryset=Store.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label=" store name"  # <--- This replaces '---------'
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label=" asin/upc code"  # <--- This replaces '---------'
    )
    
    class Meta:
        model = OrderFulfillment
        fields = [
            'store', 'product', 'code_type', 'team_code', 'supplier_order_id',
            'quantity', 'amazon_order_id', 'shipping_label_url',
            'expected_delivery_date', 'tracker_id', 'notes'
        ]
        widgets = {
            'code_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Code Type'}),
            'team_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Team Code'}),
            'supplier_order_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier Order Id'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            'amazon_order_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Amazon Order Id'}),
            'shipping_label_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Paste Shipping Label URL Here'}),
            'expected_delivery_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tracker_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tracker Id'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Notes', 'rows': 3}),
        }