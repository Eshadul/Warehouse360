from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import * # Import all new models
# Import all forms
from .forms import WarehouseForm, StoreForm, UserCreateForm, UserUpdateForm 
from django.db.models import Q # Import Q for search
from django.contrib import messages # To show success/error messages

# --- Authentication Views ---

def login_view(request):
    error = None 
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            error = "Invalid username or password"
    return render(request, 'dashboard/login.html', {'error': error})

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

# --- Main Dashboard View ---

@login_required
def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html', {'user': request.user})

# -----------------------------------------------------------------
# --- MAIN PAGE VIEWS (from Sidebar) ---
# -----------------------------------------------------------------

@login_required
def asin_upc_view(request):
    context = {
        'page_title': 'ASIN/UPC (Total: 0)',
        'user': request.user
    }
    return render(request, 'dashboard/asin_upc.html', context)

@login_required
def order_fulfillment_view(request):
    context = {
        'page_title': 'Order Fulfillment (Total: 0)',
        'user': request.user
    }
    return render(request, 'dashboard/order_fulfillment.html', context) 

# --- STORE MANAGEMENT VIEW (FUNCTIONAL + SEARCH) ---
@login_required
def store_management_view(request, pk=None):
    # Check permissions
    if not (request.user.primary_role == 'super_admin' or request.user.primary_role == 'warehouse_admin' or request.user.primary_role == 'store_manager'):
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')

    if pk:
        store = get_object_or_404(Store, pk=pk)
        form = StoreForm(instance=store)
        page_title = f"Edit Store: {store.store_name}"
    else:
        store = None
        form = StoreForm()
        page_title = "Create New Store"

    if request.method == 'POST':
        # Check create/edit permissions
        if not (request.user.primary_role == 'super_admin' or request.user.primary_role == 'warehouse_admin'):
             messages.error(request, "You do not have permission to perform this action.")
             return redirect('store_management')
        
        form = StoreForm(request.POST, instance=store)
        if form.is_valid():
            form.save()
            messages.success(request, f"Successfully saved store: {form.instance.store_name}")
            return redirect('store_management')

    # Search Logic
    query = request.GET.get('q')
    if query:
        stores = Store.objects.filter(
            Q(store_name__icontains=query) |
            Q(warehouse__name__icontains=query)
        ).order_by('-created_at')
    else:
        stores = Store.objects.all().order_by('-created_at')
    
    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'stores': stores,
        'query': query or '' 
    }
    return render(request, 'dashboard/store_management.html', context)


# --- USER CREATION VIEW (FUNCTIONAL + SEARCH) ---
@login_required
def create_user_view(request, pk=None):
    # Check view permissions
    if not (request.user.primary_role == 'super_admin' or request.user.primary_role == 'warehouse_admin'):
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')

    if pk:
        # This is an "Edit" request
        user_to_edit = get_object_or_404(User, pk=pk)
        form = UserUpdateForm(instance=user_to_edit, user=request.user)
        page_title = f"Edit User: {user_to_edit.username}"
    else:
        # This is a "Create" request
        user_to_edit = None
        form = UserCreateForm(user=request.user)
        page_title = "Create New User"

    if request.method == 'POST':
        if pk:
            form = UserUpdateForm(request.POST, instance=user_to_edit, user=request.user)
        else:
            form = UserCreateForm(request.POST, user=request.user)
        
        if form.is_valid():
            new_user = form.save()
            
            # --- Handle Many-to-Many Warehouse/Role assignments ---
            # Clear existing assignments first (important for edits)
            new_user.userwarehouserole_set.all().delete() 
            
            # Get the lists of selected warehouses and roles from the form
            warehouse_ids = request.POST.getlist('warehouses')
            role_ids = request.POST.getlist('roles')

            # Loop through selected warehouses and roles to create the links
            # This logic assumes you want to assign ALL selected roles to ALL selected warehouses
            # (e.g., if you select "Dhaka" and "Chittagong", and "Admin" and "Manager",
            # the user gets BOTH roles at BOTH warehouses)
            if warehouse_ids and role_ids:
                for w_id in warehouse_ids:
                    for r_id in role_ids:
                        warehouse = Warehouse.objects.get(id=w_id)
                        role = Role.objects.get(id=r_id)
                        UserWarehouseRole.objects.create(
                            user=new_user,
                            warehouse=warehouse,
                            role=role
                        )
            # --- End M2M logic ---
            
            messages.success(request, f"Successfully saved user: {new_user.username}")
            return redirect('create_user')
        else:
            # If form is invalid, print errors to console for debugging
            print("Form is invalid:")
            print(form.errors)


    # --- Search Logic for User List ---
    query = request.GET.get('q')
    user_list_query = User.objects.all()

    if query:
        user_list_query = user_list_query.filter(
            Q(username__icontains=query) |
            Q(full_name__icontains=query) |
            Q(email__icontains=query)
        ).order_by('username')
    
    # Filter list based on admin role
    if request.user.primary_role == 'warehouse_admin':
        # Warehouse Admins can only see/edit Managers
        user_list = user_list_query.filter(primary_role__in=['store_manager', 'warehouse_manager'])
    else:
        # Super Admins see everyone
        user_list = user_list_query.all()

    # Get all warehouses and roles to pass to the template for the dropdowns
    all_warehouses = Warehouse.objects.all()
    all_roles = Role.objects.all()

    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'users_list': user_list,
        'all_warehouses': all_warehouses,
        'all_roles': all_roles,
        'query': query or ''
    }
    return render(request, 'dashboard/create_user.html', context)


# --- WAREHOUSE VIEW (FUNCTIONAL + SEARCH) ---
@login_required
def create_warehouse_view(request, pk=None):
    # Check view permissions
    if not (request.user.primary_role == 'super_admin'):
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')
        
    if pk:
        warehouse = get_object_or_404(Warehouse, pk=pk)
        form = WarehouseForm(instance=warehouse)
        page_title = f"Edit Warehouse: {warehouse.name}"
    else:
        warehouse = None
        form = WarehouseForm()
        page_title = "Create New Warehouse"

    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            form.save()
            messages.success(request, f"Successfully saved warehouse: {form.instance.name}")
            return redirect('create_warehouse')
    
    # Search Logic
    query = request.GET.get('q')
    if query:
        warehouses = Warehouse.objects.filter(
            Q(name__icontains=query) | 
            Q(location__icontains=query)
        ).order_by('-created_at')
    else:
        warehouses = Warehouse.objects.all().order_by('-created_at')
    
    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'warehouses': warehouses,
        'query': query or '' 
    }
    return render(request, 'dashboard/create_warehouse.html', context)

# -----------------------------------------------------------------
# --- DASHBOARD CARD VIEWS ---
# -----------------------------------------------------------------

@login_required
def delivered_to_warehouse_view(request):
    context = {
        'page_title': 'Delivered to Warehouse',
        'user': request.user
    }
    return render(request, 'dashboard/summary_template.html', context)

@login_required
def out_of_stock_view(request):
    context = {
        'page_title': 'Out of Stock',
        'user': request.user
    }
    return render(request, 'dashboard/summary_template.html', context)

@login_required
def ready_to_ship_view(request):
    context = {
        'page_title': 'Ready To Shipment',
        'user': request.user
    }
    return render(request, 'dashboard/summary_template.html', context)

@login_required
def total_shipment_view(request):
    context = {
        'page_title': 'Total Shipment',
        'user': request.user
    }
    return render(request, 'dashboard/summary_template.html', context)