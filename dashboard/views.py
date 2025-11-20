from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import * # Import all new models
# Import all forms
from .forms import (
    WarehouseForm, StoreForm, 
    UserCreateForm, UserUpdateForm, UserAssignmentForm,
    ProductForm, OrderFulfillmentForm
) 
from django.db.models import Q # Import Q for search
from django.contrib import messages # To show success/error messages
from functools import wraps # For custom decorator
from django.utils import timezone # For action timestamp

# --- Authentication Views ---

def login_view(request):
    error = None 
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            
            # --- ROLE SELECTION LOGIC ---
            assignments = UserWarehouseRole.objects.filter(user=user)
            assignment_count = assignments.count()

            if assignment_count == 1:
                request.session['active_assignment_id'] = assignments.first().id
                return redirect('dashboard')
            elif assignment_count > 1:
                return redirect('select_role')
            else:
                if user.is_superuser or user.primary_role == 'super_admin':
                    return redirect('dashboard')
                else:
                    error = "You have no roles assigned to your account. Please contact an administrator."
                    logout(request) 
                    return render(request, 'dashboard/login.html', {'error': error})
            
        else:
            error = "Invalid username or password"
    return render(request, 'dashboard/login.html', {'error': error})

@login_required
def logout_view(request):
    if 'active_assignment_id' in request.session:
        del request.session['active_assignment_id']
    logout(request)
    return redirect('login')


# --- Custom Decorator for Role Check (FIXED) ---
def active_role_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Super Admins (by primary role) are special.
        if request.user.is_superuser or request.user.primary_role == 'super_admin':
            try:
                admin_role = Role.objects.get(name='super_admin')
            except Role.DoesNotExist:
                admin_role = Role(name='super_admin') 
                
            request.active_assignment = UserWarehouseRole(
                user=request.user, 
                warehouse=None, 
                role=admin_role
            )
            return view_func(request, *args, **kwargs)
            
        # All other non-super-admin users MUST have an active assignment
        if 'active_assignment_id' not in request.session:
            return redirect('select_role')
        
        try:
            assignment = UserWarehouseRole.objects.get(
                pk=request.session['active_assignment_id'], 
                user=request.user
            )
            request.active_assignment = assignment
        except UserWarehouseRole.DoesNotExist:
            del request.session['active_assignment_id']
            return redirect('select_role')
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# --- Role Selection Views ---

@login_required
def select_role_view(request):
    # 1. Get all raw assignments from database
    all_assignments = UserWarehouseRole.objects.filter(user=request.user)
    
    # 2. Group duplicates based on Warehouse + Role
    # (Ignore the specific 'Store' field for the selection card)
    unique_assignments = []
    seen_combinations = set()

    for assignment in all_assignments:
        # Create a unique key: (Warehouse ID, Role Name)
        combo = (assignment.warehouse.id, assignment.role.name)
        
        if combo not in seen_combinations:
            seen_combinations.add(combo)
            unique_assignments.append(assignment)

    # 3. Auto-Redirect Logic (Based on UNIQUE groups)
    # If the user effectively has only 1 role context (even if multiple stores), auto-login.
    is_superuser_or_global = (request.user.is_superuser or request.user.primary_role == 'super_admin')

    if len(unique_assignments) == 1 and not is_superuser_or_global:
        request.session['active_assignment_id'] = unique_assignments[0].id
        return redirect('dashboard')
    
    if len(unique_assignments) == 0 and is_superuser_or_global:
        return redirect('dashboard')

    return render(request, 'dashboard/select_role.html', {
        'assignments': unique_assignments, # Pass the deduped list
        'user': request.user
    })

@login_required
def set_active_role(request, assignment_id):
    try:
        assignment = UserWarehouseRole.objects.get(pk=assignment_id, user=request.user)
        request.session['active_assignment_id'] = assignment.id
        return redirect('dashboard')
    except UserWarehouseRole.DoesNotExist:
        messages.error(request, "Invalid role selection.")
        return redirect('select_role')


# --- Main Dashboard View ---
@login_required
@active_role_required 
def dashboard_view(request):
    # --- Get Dashboard Card Counts ---
    
    orders_query = OrderFulfillment.objects.all()
    
    # Filter by warehouse if not Super Admin
    if request.user.primary_role != 'super_admin' and request.active_assignment.warehouse is not None:
        orders_query = orders_query.filter(store__warehouse=request.active_assignment.warehouse)
    
    delivered_count = orders_query.filter(status='delivered').count()
    out_of_stock_count = orders_query.filter(status='out_of_stock').count()
    ready_to_ship_count = orders_query.filter(status='ready_to_ship').count()
    total_shipment_count = orders_query.filter(status='completed').count()

    context = {
        'user': request.user,
        'active_assignment': getattr(request, 'active_assignment', None),
        'delivered_count': delivered_count,
        'out_of_stock_count': out_of_stock_count,
        'ready_to_ship_count': ready_to_ship_count,
        'total_shipment_count': total_shipment_count,
    }
    return render(request, 'dashboard/dashboard.html', context)

# -----------------------------------------------------------------
# --- MAIN PAGE VIEWS (from Sidebar) ---
# -----------------------------------------------------------------

# --- ASIN/UPC VIEW (FUNCTIONAL) ---
@login_required
@active_role_required
def asin_upc_view(request, pk=None):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)
    
    # Warehouse Managers usually don't access this, based on your previous rules
    if active_role_name == 'warehouse_manager':
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')
    
    if pk:
        product = get_object_or_404(Product, pk=pk)
        # Security: Store Manager can only edit their own products
        if active_role_name == 'store_manager' and product.created_by != request.user:
             messages.error(request, "You cannot edit products created by others.")
             return redirect('asin_upc')
             
        form = ProductForm(instance=product)
        page_title = f"Edit Product: {product.code}"
    else:
        product = None
        form = ProductForm()
        page_title = "Create New ASIN/UPC"

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            new_product = form.save(commit=False)
            if not pk:
                new_product.created_by = request.user 
            new_product.save()
            messages.success(request, f"Successfully saved product: {new_product.code}")
            return redirect('asin_upc')

    # --- LIST VISIBILITY LOGIC ---
    can_view_list = False
    products = Product.objects.none() 
    query = request.GET.get('q')
    
    # Allow Super Admin, Warehouse Admin, AND Store Manager to view list
    if active_role_name in ['super_admin', 'warehouse_admin', 'store_manager']:
        can_view_list = True
        
        products_query = Product.objects.all()

        # --- FILTER: STORE MANAGER SEES ONLY THEIR OWN CREATIONS ---
        if active_role_name == 'store_manager':
            products_query = products_query.filter(created_by=request.user)

        if query:
            products_query = products_query.filter(
                Q(product_name__icontains=query) |
                Q(code__icontains=query) |
                Q(code_type__icontains=query)
            ).distinct()
        
        products = products_query.order_by('-created_at')

    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'products': products,
        'can_view_list': can_view_list,
        'query': query or '',
        'active_assignment': active_assignment
    }
    return render(request, 'dashboard/asin_upc.html', context)

# --- ORDER FULFILLMENT VIEW (LOGIC FIX) ---
@login_required
@active_role_required
def order_fulfillment_view(request, pk=None):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)
    
    # --- 1. PERMISSIONS & CAPABILITIES ---
    can_view_list = False
    can_create_or_edit = False
    
    if active_role_name in ['super_admin', 'warehouse_admin']:
        can_view_list = True
        can_create_or_edit = True
    elif active_role_name == 'store_manager':
        can_view_list = True  # <--- ENABLED LIST FOR STORE MANAGER
        can_create_or_edit = True
    elif active_role_name == 'warehouse_manager':
        can_view_list = True
        can_create_or_edit = False

    # --- 2. FORM SETUP ---
    if pk:
        order = get_object_or_404(OrderFulfillment, pk=pk)
        # Security: Store Manager can only edit their own orders
        if active_role_name == 'store_manager' and order.created_by != request.user:
             messages.error(request, "You cannot edit orders created by others.")
             return redirect('order_fulfillment')
             
        form = OrderFulfillmentForm(instance=order)
        page_title = f"Edit Order: {order.supplier_order_id or order.id}"
    else:
        order = None
        form = OrderFulfillmentForm()
        page_title = "Create New Order Fulfillment"
        
    # --- 3. FILTER FORM DROPDOWN (Strict Store Assignment) ---
    if active_role_name == 'store_manager':
        # Find all stores assigned to this user in the current warehouse
        my_store_ids = UserWarehouseRole.objects.filter(
            user=request.user, 
            warehouse=active_assignment.warehouse,
            role__name='store_manager'
        ).values_list('store_id', flat=True)
        
        form.fields['store'].queryset = Store.objects.filter(id__in=my_store_ids)
    elif active_role_name == 'warehouse_admin' or active_role_name == 'warehouse_manager':
        form.fields['store'].queryset = Store.objects.filter(warehouse=active_assignment.warehouse)
    # Super admin sees all (default)

    form.fields['product'].queryset = Product.objects.all() 

    # --- 4. HANDLE POST ---
    if request.method == 'POST':
        if not can_create_or_edit:
             messages.error(request, "You do not have permission to perform this action.")
             return redirect('order_fulfillment')
        
        form = OrderFulfillmentForm(request.POST, instance=order)
        if form.is_valid():
            new_order = form.save(commit=False)
            if not pk: 
                new_order.created_by = request.user
            new_order.save()
            messages.success(request, f"Successfully saved order.")
            return redirect('order_fulfillment')

    # --- 5. FILTER LIST VIEW ---
    orders = OrderFulfillment.objects.none()
    query = request.GET.get('q')
    
    if can_view_list:
        # Start with all pending orders
        orders_query = OrderFulfillment.objects.filter(status='pending')

        # APPLY FILTERS BASED ON ROLE
        if active_role_name == 'store_manager':
            # Requirement: ONLY see orders created by SELF
            orders_query = orders_query.filter(created_by=request.user)
            
        elif active_role_name in ['warehouse_manager', 'warehouse_admin']:
            # They see everything in the warehouse
            orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)
        
        # Apply Search
        if query:
            orders_query = orders_query.filter(
                Q(product__product_name__icontains=query) |
                Q(store__store_name__icontains=query) |
                Q(supplier_order_id__icontains=query) |
                Q(amazon_order_id__icontains=query) |
                Q(tracker_id__icontains=query)
            ).distinct()
        
        orders = orders_query.order_by('-created_at') 

    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'orders': orders,
        'can_view_list': can_view_list,
        'can_create_or_edit': can_create_or_edit,
        'query': query or '',
        'active_assignment': active_assignment
    }
    return render(request, 'dashboard/order_fulfillment.html', context)

# --- ORDER FULFILLMENT ACTION (DTW/OfS) - PERMISSION FIX ---
@login_required
@active_role_required
def order_fulfillment_action(request, pk, action_type):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    if not (active_role_name == 'warehouse_manager' or active_role_name == 'super_admin' or active_role_name == 'warehouse_admin'):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('order_fulfillment')
    
    order = get_object_or_404(OrderFulfillment, pk=pk)
    
    if active_role_name != 'super_admin' and order.store.warehouse != active_assignment.warehouse:
        messages.error(request, "You are not assigned to this order's warehouse.")
        return redirect('order_fulfillment')

    if action_type == 'dtw': 
        order.status = 'delivered'
        order.action_taken_by = request.user
        order.action_taken_at = timezone.now()
        order.save()
        messages.success(request, f"Order {order.id} marked as 'Delivered to Warehouse'.")
    elif action_type == 'ofs': 
        order.status = 'out_of_stock'
        order.action_taken_by = request.user
        order.action_taken_at = timezone.now()
        order.save()
        messages.success(request, f"Order {order.id} marked as 'Out of Stock'.")
    else:
        messages.error(request, "Invalid action.")

    return redirect('order_fulfillment')


# --- STORE MANAGEMENT VIEW (FUNCTIONAL + SEARCH) ---
@login_required
@active_role_required
def store_management_view(request, pk=None):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)
    
    # --- 1. Permission Check ---
    # Allowed: Super Admin, Warehouse Admin, Warehouse Manager, Store Manager
    if active_role_name not in ['super_admin', 'warehouse_admin', 'store_manager', 'warehouse_manager']:
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')

    # --- 2. Determine Capabilities ---
    # Only Admins can create/edit stores.
    can_create_store = (active_role_name == 'super_admin' or active_role_name == 'warehouse_admin')

    # If a non-admin tries to access the 'Edit' URL, kick them out.
    if pk and not can_create_store:
        messages.error(request, "You do not have permission to edit stores.")
        return redirect('store_management')

    # --- 3. Form Setup ---
    if pk:
        store = get_object_or_404(Store, pk=pk)
        form = StoreForm(instance=store)
        page_title = f"Edit Store: {store.store_name}"
    else:
        store = None
        form = StoreForm()
        page_title = "Store Management"

    # --- 4. Handle POST (Create/Update) ---
    if request.method == 'POST':
        if not can_create_store:
             messages.error(request, "You do not have permission to perform this action.")
             return redirect('store_management')
        
        form = StoreForm(request.POST, instance=store)
        if form.is_valid():
            # If Warehouse Admin, force the warehouse to be their own
            if active_role_name == 'warehouse_admin':
                form.instance.warehouse = active_assignment.warehouse
            
            form.save()
            messages.success(request, f"Successfully saved store: {form.instance.store_name}")
            return redirect('store_management')

    # --- 5. Search & Filter Logic ---
    query = request.GET.get('q')
    stores_query = Store.objects.all() 

    # === FILTERING BASED ON ROLE ===
    
    if active_role_name in ['warehouse_admin', 'warehouse_manager']:
        # Scenario A: Admin/Manager sees ALL stores in THEIR warehouse
        stores_query = stores_query.filter(warehouse=active_assignment.warehouse)
        
    elif active_role_name == 'store_manager':
        # Scenario B: Store Manager sees ALL stores assigned to them in this warehouse
        # We query the UserWarehouseRole table to find every store ID linked to this user+warehouse
        
        my_store_ids = UserWarehouseRole.objects.filter(
            user=request.user,
            warehouse=active_assignment.warehouse,
            role__name='store_manager'
        ).values_list('store_id', flat=True)
        
        # Filter the main list to only show these IDs
        stores_query = stores_query.filter(id__in=my_store_ids)

    # Apply Text Search
    if query:
        text_query = (
            Q(store_name__icontains=query) |
            Q(warehouse__name__icontains=query) |
            Q(store_type__icontains=query) 
        )
        stores_query = stores_query.filter(text_query).distinct()
    
    stores = stores_query.order_by('-created_at')
    
    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'stores': stores,
        'query': query or '',
        'active_assignment': active_assignment,
        'can_create_store': can_create_store, 
    }
    return render(request, 'dashboard/store_management.html', context)
# --- USER CREATION VIEW (PERMISSION FIX) ---
@login_required
@active_role_required
def create_user_view(request, pk=None):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)
    
    # --- 1. PERMISSION CHECK ---
    if active_role_name not in ['super_admin', 'warehouse_admin']:
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')

    # --- 2. SETUP FORMS ---
    if pk:
        # Edit Mode
        user_to_edit = get_object_or_404(User, pk=pk)
        user_form = UserUpdateForm(instance=user_to_edit, user=request.user)
        page_title = f"Edit User: {user_to_edit.username}"
        assignment_form = UserAssignmentForm(user=request.user, active_assignment=active_assignment) 
        current_assignments = user_to_edit.userwarehouserole_set.all().order_by('warehouse__name')
    else:
        # Create Mode
        user_to_edit = None
        user_form = UserCreateForm(user=request.user)
        page_title = "Create New User"
        assignment_form = UserAssignmentForm(user=request.user, active_assignment=active_assignment) 
        current_assignments = None 

    # --- 3. HANDLE SAVE / UPDATE ---
    if request.method == 'POST':
        
        # A. SAVE USER (Main Form)
        if 'save_user' in request.POST:
            if pk:
                # Update existing
                user_form = UserUpdateForm(request.POST, instance=user_to_edit, user=request.user)
                if user_form.is_valid():
                    user_form.save()
                    messages.success(request, "User updated successfully.")
                    return redirect('user_update', pk=pk)
            else:
                # Create new
                user_form = UserCreateForm(request.POST, user=request.user)
                assignment_form = UserAssignmentForm(request.POST, user=request.user, active_assignment=active_assignment)
                
                if user_form.is_valid() and assignment_form.is_valid():
                    saved_user = user_form.save()
                    
                    # Create the initial assignment
                    new_assignment = assignment_form.save(commit=False)
                    new_assignment.user = saved_user
                    new_assignment.save()
                    
                    messages.success(request, f"User {saved_user.username} created successfully.")
                    return redirect('user_update', pk=saved_user.pk)
                else:
                    messages.error(request, "Please correct the errors below.")

        # B. ADD ASSIGNMENT (Edit Mode Only)
        elif 'add_assignment' in request.POST:
            if not pk: return redirect('dashboard')
            
            assignment_form = UserAssignmentForm(request.POST, user=request.user, active_assignment=active_assignment)
            if assignment_form.is_valid():
                warehouse = assignment_form.cleaned_data['warehouse']
                role = assignment_form.cleaned_data['role']
                store = assignment_form.cleaned_data.get('store') # <--- 1. GET STORE
                
                # --- 2. UPDATED DUPLICATE CHECK ---
                # We now include 'store=store' in the filter. 
                # This allows the same role at the same warehouse IF the store is different.
                if UserWarehouseRole.objects.filter(user=user_to_edit, warehouse=warehouse, role=role, store=store).exists():
                    if store:
                        messages.error(request, f"User is already assigned to '{store.store_name}'.")
                    else:
                        messages.error(request, "Role already assigned at this warehouse.")
                else:
                    new_assignment = assignment_form.save(commit=False)
                    new_assignment.user = user_to_edit
                    new_assignment.save()
                    messages.success(request, "Assignment added.")
                return redirect('user_update', pk=pk) 
            else:
                # If form is invalid, we redirect back (errors will be lost unless we render, but redirect is safer for now)
                messages.error(request, "Invalid assignment details.")
                return redirect('user_update', pk=pk)

    # --- 4. LIST FILTERING LOGIC ---
    user_list_query = User.objects.all().order_by('-date_joined')

    query = request.GET.get('q')
    if query:
        user_list_query = user_list_query.filter(
            Q(username__icontains=query) |
            Q(full_name__icontains=query) |
            Q(email__icontains=query)
        )

    if active_role_name == 'warehouse_admin':
        current_warehouse = active_assignment.warehouse
        user_list_query = user_list_query.filter(
            userwarehouserole__warehouse=current_warehouse
        ).distinct()

    context = {
        'page_title': page_title,
        'user': request.user,
        'form': user_form, 
        'assignment_form': assignment_form, 
        'user_to_edit': user_to_edit, 
        'current_assignments': current_assignments,
        'users_list': user_list_query,
        'query': query or '',
        'active_assignment': active_assignment,
        'all_warehouses': Warehouse.objects.all(),
        'all_roles': Role.objects.all(), 
    }
    return render(request, 'dashboard/create_user.html', context)
# --- DELETE USER ASSIGNMENT (PERMISSION FIX) ---
@login_required
def delete_user_assignment(request, pk):
    try:
        assignment = get_object_or_404(UserWarehouseRole, pk=pk)
        user_pk = assignment.user.pk 
        
        active_role_name = getattr(request.active_assignment.role, 'name', None)
        
        if not (active_role_name == 'super_admin' or active_role_name == 'warehouse_admin'):
            messages.error(request, "You do not have permission to delete this.")
            return redirect('user_update', pk=user_pk)
        
        assignment.delete()
        messages.success(request, "Assignment removed.")
        return redirect('user_update', pk=user_pk)

    except Exception as e:
        messages.error(request, f"Error removing assignment: {e}")
        return redirect('create_user')


# --- WAREHOUSE VIEW (PERMISSION FIX) ---
@login_required
@active_role_required
def create_warehouse_view(request, pk=None):
    active_role_name = getattr(request.active_assignment.role, 'name', None)
    
    if not (active_role_name == 'super_admin'):
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
        'query': query or '',
        'active_assignment': getattr(request, 'active_assignment', None)
    }
    return render(request, 'dashboard/create_warehouse.html', context)

# -----------------------------------------------------------------
# --- DASHBOARD CARD VIEWS (NOW FUNCTIONAL) ---
# -----------------------------------------------------------------

@login_required
@active_role_required
def delivered_to_warehouse_view(request):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    can_take_action = (
        active_role_name == 'super_admin' or
        active_role_name == 'warehouse_admin' or
        active_role_name == 'warehouse_manager'
    )

    orders_query = OrderFulfillment.objects.filter(status='delivered')
    
    if active_role_name == 'warehouse_manager' or active_role_name == 'warehouse_admin':
        orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)

    query = request.GET.get('q')
    if query:
        orders_query = orders_query.filter(
            Q(product__product_name__icontains=query) |
            Q(store__store_name__icontains=query) |
            Q(supplier_order_id__icontains=query) |
            Q(amazon_order_id__icontains=query) |
            Q(tracker_id__icontains=query)
        ).distinct()

    orders = orders_query.order_by('-action_taken_at') 

    context = {
        'page_title': 'Delivered to Warehouse',
        'user': request.user,
        'orders': orders,
        'can_take_action': can_take_action,
        'query': query or '',
        'active_assignment': active_assignment
    }
    return render(request, 'dashboard/delivered_to_warehouse.html', context)

# --- RTS ACTION VIEW ---
@login_required
@active_role_required
def rts_action_view(request, pk):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    if not (active_role_name == 'super_admin' or
            active_role_name == 'warehouse_admin' or
            active_role_name == 'warehouse_manager'):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('delivered_to_warehouse')
    
    order = get_object_or_404(OrderFulfillment, pk=pk)
    
    if active_role_name != 'super_admin' and order.store.warehouse != active_assignment.warehouse:
        messages.error(request, "You are not assigned to this order's warehouse.")
        return redirect('delivered_to_warehouse')

    order.status = 'ready_to_ship'
    order.action_taken_by = request.user 
    order.action_taken_at = timezone.now() 
    order.save()
    
    messages.success(request, f"Order {order.id} marked as 'Ready To Shipment'.")
    return redirect('delivered_to_warehouse') 

# --- OUT OF STOCK VIEW (NOW FUNCTIONAL) ---
@login_required
@active_role_required
def out_of_stock_view(request):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    can_take_action = (
        active_role_name == 'super_admin' or
        active_role_name == 'warehouse_admin' or
        active_role_name == 'warehouse_manager'
    )

    orders_query = OrderFulfillment.objects.filter(status='out_of_stock')
    
    if active_role_name == 'warehouse_manager' or active_role_name == 'warehouse_admin':
        orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)

    query = request.GET.get('q')
    if query:
        orders_query = orders_query.filter(
            Q(product__product_name__icontains=query) |
            Q(store__store_name__icontains=query) |
            Q(supplier_order_id__icontains=query) |
            Q(amazon_order_id__icontains=query) |
            Q(tracker_id__icontains=query)
        ).distinct()

    orders = orders_query.order_by('-action_taken_at') 

    context = {
        'page_title': 'Out of Stock',
        'user': request.user,
        'orders': orders,
        'can_take_action': can_take_action,
        'query': query or '',
        'active_assignment': active_assignment
    }
    return render(request, 'dashboard/out_of_stock.html', context)

# --- OfS to DTW ACTION VIEW (FIXED TYPO) ---
@login_required
@active_role_required
def ofs_to_dtw_action_view(request, pk):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    # Permission check: Only Admins or Warehouse Manager
    if not (active_role_name == 'super_admin' or
            active_role_name == 'warehouse_admin' or
            active_role_name == 'warehouse_manager'):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('out_of_stock')
    
    order = get_object_or_404(OrderFulfillment, pk=pk)
    
    # Security Check: Bypass warehouse check for Super Admin
    if active_role_name != 'super_admin' and order.store.warehouse != active_assignment.warehouse:
        messages.error(request, "You are not assigned to this order's warehouse.")
        return redirect('out_of_stock')

    # Update the status BACK to 'delivered'
    order.status = 'delivered'
    order.action_taken_by = request.user 
    order.action_taken_at = timezone.now() 
    order.save()
    
    messages.success(request, f"Order {order.id} moved back to 'Delivered to Warehouse'.")
    return redirect('out_of_stock') # Redirect back to the OfS list


# --- READY TO SHIP VIEW (NOW FUNCTIONAL) ---
@login_required
@active_role_required
def ready_to_ship_view(request):
    """
    This page shows a list of all orders that have been marked
    'ready_to_ship'. This is the final step in this queue.
    """
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    can_take_action = (
        active_role_name == 'super_admin' or
        active_role_name == 'warehouse_admin' or
        active_role_name == 'warehouse_manager'
    )

    # --- List & Search Logic ---
    orders_query = OrderFulfillment.objects.filter(status='ready_to_ship')
    
    # Filter list based on role
    if active_role_name == 'warehouse_manager' or active_role_name == 'warehouse_admin':
        orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)
    # Super Admin sees all

    query = request.GET.get('q')
    if query:
        orders_query = orders_query.filter(
            Q(product__product_name__icontains=query) |
            Q(store__store_name__icontains=query) |
            Q(supplier_order_id__icontains=query) |
            Q(amazon_order_id__icontains=query) |
            Q(tracker_id__icontains=query)
        ).distinct()

    orders = orders_query.order_by('-action_taken_at') # Show newest RTS first

    context = {
        'page_title': 'Ready To Shipment',
        'user': request.user,
        'orders': orders,
        'can_take_action': can_take_action,
        'query': query or '',
        'active_assignment': active_assignment
    }
    return render(request, 'dashboard/ready_to_ship.html', context)

# --- NEW: CS (COMPLETE SHIPMENT) ACTION VIEW ---
@login_required
@active_role_required
def cs_action_view(request, pk):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    # Permission check: Only Admins or Warehouse Manager
    if not (active_role_name == 'super_admin' or
            active_role_name == 'warehouse_admin' or
            active_role_name == 'warehouse_manager'):
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('ready_to_ship') # Redirect back to RTS page
    
    order = get_object_or_404(OrderFulfillment, pk=pk)
    
    # Security Check: Bypass warehouse check for Super Admin
    if active_role_name != 'super_admin' and order.store.warehouse != active_assignment.warehouse:
        messages.error(request, "You are not assigned to this order's warehouse.")
        return redirect('ready_to_ship')

    # Update the status to 'completed'
    order.status = 'completed'
    order.action_taken_by = request.user 
    order.action_taken_at = timezone.now() 
    order.save()
    
    messages.success(request, f"Order {order.id} marked as 'Completed'.")
    return redirect('ready_to_ship') # Redirect back to RTS page


# --- TOTAL SHIPMENT VIEW (NOW FUNCTIONAL) ---
@login_required
@active_role_required
def total_shipment_view(request):
    """
    This page shows a list of all orders that have been marked
    'completed'. This is the final step.
    """
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    # --- List & Search Logic ---
    orders_query = OrderFulfillment.objects.filter(status='completed')
    
    # Filter list based on role
    if active_role_name == 'warehouse_manager' or active_role_name == 'warehouse_admin':
        orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)
    # Super Admin sees all

    query = request.GET.get('q')
    if query:
        orders_query = orders_query.filter(
            Q(product__product_name__icontains=query) |
            Q(store__store_name__icontains=query) |
            Q(supplier_order_id__icontains=query) |
            Q(amazon_order_id__icontains=query) |
            Q(tracker_id__icontains=query)
        ).distinct()

    orders = orders_query.order_by('-action_taken_at') # Show newest completed first

    context = {
        'page_title': 'Total Shipment (Completed)',
        'user': request.user,
        'orders': orders,
        'query': query or '',
        'active_assignment': active_assignment
    }
    # We will create this new template in the next step
    return render(request, 'dashboard/total_shipment.html', context)


# --- DELETE USER VIEW ---
@login_required
def delete_user_view(request, pk):
    # Permission Check
    if not (request.user.primary_role == 'super_admin' or request.user.primary_role == 'warehouse_admin'):
        messages.error(request, "You do not have permission to delete users.")
        return redirect('create_user')

    try:
        user_to_delete = get_object_or_404(User, pk=pk)
        
        # Prevent deleting yourself
        if user_to_delete == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('create_user')
            
        # Prevent deleting Super Admins (unless you are one, logic can be refined)
        if user_to_delete.primary_role == 'super_admin' and request.user.primary_role != 'super_admin':
             messages.error(request, "You cannot delete a Super Admin.")
             return redirect('create_user')

        user_to_delete.delete()
        messages.success(request, f"User {user_to_delete.username} deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting user: {e}")
        
    return redirect('create_user')

# --- DELETE STORE VIEW ---
@login_required
def delete_store_view(request, pk):
    # Permission Check
    if not (request.user.primary_role == 'super_admin' or request.user.primary_role == 'warehouse_admin'):
        messages.error(request, "You do not have permission to delete stores.")
        return redirect('store_management')

    try:
        store = get_object_or_404(Store, pk=pk)
        store.delete()
        messages.success(request, f"Store {store.store_name} deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting store: {e}")

    return redirect('store_management')

# --- DELETE WAREHOUSE VIEW ---
@login_required
def delete_warehouse_view(request, pk):
    # Permission Check (Super Admin Only)
    if not (request.user.primary_role == 'super_admin'):
        messages.error(request, "You do not have permission to delete warehouses.")
        return redirect('create_warehouse')

    try:
        warehouse = get_object_or_404(Warehouse, pk=pk)
        warehouse.delete()
        messages.success(request, f"Warehouse {warehouse.name} deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting warehouse: {e}")

    return redirect('create_warehouse')

def load_stores_ajax(request):
    warehouse_id = request.GET.get('warehouse_id')
    stores = Store.objects.filter(warehouse_id=warehouse_id).order_by('store_name')
    return JsonResponse(list(stores.values('id', 'store_name')), safe=False)