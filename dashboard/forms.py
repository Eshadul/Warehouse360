from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Warehouse, Store, User, Role
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
    class Meta:
        model = Store
        fields = ['warehouse', 'store_name', 'store_type', 'is_active']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'store_name': forms.TextInput(attrs={'class': 'form-control'}),
            'store_type': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.Select(attrs={'class': 'form-select'}),
        }

# --- User Create Form ---
# This form INCLUDES password validation and is used for CREATING new users.
class UserCreateForm(UserCreationForm):
    # We add our custom fields here
    full_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    primary_role = forms.ChoiceField(
        choices=User.ROLE_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta(UserCreationForm.Meta):
        model = User # Tell the form which model to use
        # Define ALL fields (except password/password2, which UserCreationForm adds)
        fields = ('username', 'full_name', 'email', 'phone_number', 'primary_role') 

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None) # Get the logged-in user
        super().__init__(*args, **kwargs)
        
        # === THIS IS THE FIX ===
        # The correct field names in UserCreationForm are 'password1' and 'password2'
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
        
        # Optional: Add nicer labels
        self.fields['password1'].label = "Password"
        self.fields['password2'].label = "Confirm Password"
        # === END FIX ===

        # Super Admins can create any role
        if self.user and self.user.primary_role == 'super_admin':
             self.fields['primary_role'].choices = User.ROLE_CHOICES
        # Warehouse Admins can only create managers
        elif self.user and self.user.primary_role == 'warehouse_admin':
            self.fields['primary_role'].choices = [
                ('store_manager', 'Store Manager'),
                ('warehouse_manager', 'Warehouse Manager'),
            ]

# --- User Update Form ---
# This form is for EDITING existing users. Passwords are OPTIONAL.
class UserUpdateForm(forms.ModelForm):
    # Add optional password fields (these names are correct: 'password' and 'password2')
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
        self.user = kwargs.pop('user', None) # Get the logged-in user
        super().__init__(*args, **kwargs)

        # Super Admins can edit any role
        if self.user and self.user.primary_role == 'super_admin':
             self.fields['primary_role'].choices = User.ROLE_CHOICES
        # Warehouse Admins can only edit/assign manager roles
        elif self.user and self.user.primary_role == 'warehouse_admin':
            self.fields['primary_role'].choices = [
                ('store_manager', 'Store Manager'),
                ('warehouse_manager', 'Warehouse Manager'),
            ]

    def clean(self):
        # Check if passwords match (only if they were provided)
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password2 = cleaned_data.get("password2")

        if password and password != password2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        # Save the user instance
        user = super().save(commit=False)
        
        # Check if a new password was entered
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password) # Hash and set the new password

        if commit:
            user.save()
        return user