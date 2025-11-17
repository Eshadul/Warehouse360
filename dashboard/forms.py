from django import forms
from django.contrib.auth.forms import UserCreationForm
# Import all the models we need for the forms
from .models import (
    Warehouse, Store, User, Role, UserWarehouseRole, Product, OrderFulfillment
) 
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

# --- User Create Form ---
class UserCreateForm(UserCreationForm):
    full_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    primary_role = forms.ChoiceField(
        choices=User.ROLE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta(UserCreationForm.Meta):
        model = User 
        fields = ('username', 'full_name', 'email', 'phone_number', 'primary_role') 

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

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'phone_number', 'primary_role', 'is_active']
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
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all(), 
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(), 
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs)

        if user and (user.primary_role == 'warehouse_admin' or (user.active_assignment and user.active_assignment.role.name == 'warehouse_admin')):
            self.fields['role'].queryset = Role.objects.filter(
                name__in=['store_manager', 'warehouse_manager']
            )
        elif user and (user.primary_role == 'super_admin' or (user.active_assignment and user.active_assignment.role.name == 'super_admin')):
            self.fields['role'].queryset = Role.objects.all()
        else:
            self.fields['role'].queryset = Role.objects.none()

    class Meta:
        model = UserWarehouseRole
        fields = ['warehouse', 'role']


# --- Product (ASIN/UPC) Form ---
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['code', 'product_name', 'code_type', 'product_image_link', 'minimum_price']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Code'}),
            'product_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product Name'}),
            'code_type': forms.Select(attrs={'class': 'form-select'}),
            'product_image_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Product Image Link'}),
            'minimum_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Minimum Price'}),
        }

# --- NEW: Order Fulfillment Form ---
class OrderFulfillmentForm(forms.ModelForm):
    # We will dynamically filter these querysets in the view
    store = forms.ModelChoiceField(
        queryset=Store.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = OrderFulfillment
        # All fields except the status and tracking fields
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