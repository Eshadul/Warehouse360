from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
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
    assignments = UserWarehouseRole.objects.filter(user=request.user)
    
    if assignments.count() == 1 and not (request.user.is_superuser or request.user.primary_role == 'super_admin'):
        request.session['active_assignment_id'] = assignments.first().id
        return redirect('dashboard')
    
    if assignments.count() == 0 and (request.user.is_superuser or request.user.primary_role == 'super_admin'):
        return redirect('dashboard')

    return render(request, 'dashboard/select_role.html', {
        'assignments': assignments,
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
    # 'Total Shipment' card will show COMPLETED orders
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
    active_role_name = getattr(request.active_assignment.role, 'name', None)
    
    if active_role_name == 'warehouse_manager':
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')
    
    if pk:
        product = get_object_or_404(Product, pk=pk)
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
            new_product.created_by = request.user 
            new_product.save()
            messages.success(request, f"Successfully saved product: {new_product.code}")
            return redirect('asin_upc')

    can_view_list = False
    products = Product.objects.none() 
    query = request.GET.get('q')
    
    if active_role_name == 'super_admin' or active_role_name == 'warehouse_admin':
        can_view_list = True
        
        products_query = Product.objects.all()
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
        'active_assignment': getattr(request, 'active_assignment', None)
    }
    return render(request, 'dashboard/asin_upc.html', context)


# --- ORDER FULFILLMENT VIEW (LOGIC FIX) ---
@login_required
@active_role_required
def order_fulfillment_view(request, pk=None):
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)
    
    can_view_list = False
    can_create_or_edit = False
    
    if active_role_name == 'super_admin' or active_role_name == 'warehouse_admin':
        can_view_list = True
        can_create_or_edit = True
    elif active_role_name == 'store_manager':
        can_view_list = False 
        can_create_or_edit = True
    elif active_role_name == 'warehouse_manager':
        can_view_list = True
        can_create_or_edit = False

    if pk:
        order = get_object_or_404(OrderFulfillment, pk=pk)
        form = OrderFulfillmentForm(instance=order)
        page_title = f"Edit Order: {order.supplier_order_id or order.id}"
    else:
        order = None
        form = OrderFulfillmentForm()
        page_title = "Create New Order Fulfillment"
        
    if active_role_name == 'super_admin':
        form.fields['store'].queryset = Store.objects.all()
    else:
        form.fields['store'].queryset = Store.objects.filter(warehouse=active_assignment.warehouse)
    
    form.fields['product'].queryset = Product.objects.all() 

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

    orders = OrderFulfillment.objects.none()
    query = request.GET.get('q')
    
    if can_view_list:
        orders_query = OrderFulfillment.objects.filter(status='pending')

        if active_role_name == 'warehouse_manager' or active_role_name == 'warehouse_admin':
            orders_query = orders_query.filter(store__warehouse=active_assignment.warehouse)
        
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
    active_role_name = getattr(request.active_assignment.role, 'name', None)
    
    if not (active_role_name == 'super_admin' or active_role_name == 'warehouse_admin' or active_role_name == 'store_manager'):
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
        if not (active_role_name == 'super_admin' or active_role_name == 'warehouse_admin'):
             messages.error(request, "You do not have permission to perform this action.")
             return redirect('store_management')
        
        form = StoreForm(request.POST, instance=store)
        if form.is_valid():
            form.save()
            messages.success(request, f"Successfully saved store: {form.instance.store_name}")
            return redirect('store_management')

    # Search Logic
    query = request.GET.get('q')
    stores_query = Store.objects.all() 

    if query:
        text_query = (
            Q(store_name__icontains=query) |
            Q(warehouse__name__icontains=query) |
            Q(store_type__icontains=query) |
            Q(created_at__icontains=query) 
        )
        status_query = Q()
        if 'active'.startswith(query.lower()):
            status_query = Q(is_active=True)
        elif 'inactive'.startswith(query.lower()):
            status_query = Q(is_active=False)
        stores_query = stores_query.filter(text_query | status_query).distinct()
    
    stores = stores_query.order_by('-created_at')
    
    context = {
        'page_title': page_title,
        'user': request.user,
        'form': form,
        'stores': stores,
        'query': query or '',
        'active_assignment': getattr(request, 'active_assignment', None)
    }
    return render(request, 'dashboard/store_management.html', context)


# --- USER CREATION VIEW (PERMISSION FIX) ---
@login_required
@active_role_required
def create_user_view(request, pk=None):
    active_role_name = getattr(request.active_assignment.role, 'name', None)
    
    if not (active_role_name == 'super_admin' or active_role_name == 'warehouse_admin'):
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')

    if pk:
        user_to_edit = get_object_or_404(User, pk=pk)
        user_form = UserUpdateForm(instance=user_to_edit, user=request.user)
        page_title = f"Edit User: {user_to_edit.username}"
        assignment_form = UserAssignmentForm(user=request.user) 
        current_assignments = user_to_edit.userwarehouserole_set.all().order_by('warehouse__name')
    else:
        user_to_edit = None
        user_form = UserCreateForm(user=request.user)
        page_title = "Create New User"
        assignment_form = None 
        current_assignments = None 

    if request.method == 'POST':
        
        if 'save_user' in request.POST:
            if pk:
                user_form = UserUpdateForm(request.POST, instance=user_to_edit, user=request.user)
            else:
                user_form = UserCreateForm(request.POST, user=request.user)
            
            if user_form.is_valid():
                saved_user = user_form.save()
                messages.success(request, f"Successfully saved user: {saved_user.username}")
                if not pk:
                    return redirect('user_update', pk=saved_user.pk)
                return redirect('user_update', pk=pk)
            else:
                print("User form invalid:", user_form.errors) 

        elif 'add_assignment' in request.POST:
            if not pk: 
                return redirect('dashboard')
            
            assignment_form = UserAssignmentForm(request.POST, user=request.user)
            if assignment_form.is_valid():
                warehouse = assignment_form.cleaned_data['warehouse']
                role = assignment_form.cleaned_data['role']
                
                if UserWarehouseRole.objects.filter(user=user_to_edit, warehouse=warehouse, role=role).exists():
                    messages.error(request, f"This user already has the role '{role}' at '{warehouse}'.")
                else:
                    new_assignment = assignment_form.save(commit=False)
                    new_assignment.user = user_to_edit
                    new_assignment.save()
                    messages.success(request, "Assignment added.")
                return redirect('user_update', pk=pk) 
            else:
                print("Assignment form invalid:", assignment_form.errors) 

    # --- Search Logic for User List ---
    query = request.GET.get('q')
    user_list_query = User.objects.all()

    if query:
        user_list_query = user_list_query.filter(
            Q(username__icontains=query) |
            Q(full_name__icontains=query) |
            Q(email__icontains=query)
        ).order_by('username')
    
    if request.user.primary_role == 'warehouse_admin':
        user_list = user_list_query.filter(primary_role__in=['store_manager', 'warehouse_manager'])
    else:
        user_list = user_list_query.all()

    all_warehouses = Warehouse.objects.all()
    all_roles = Role.objects.all() 

    context = {
        'page_title': page_title,
        'user': request.user,
        'form': user_form, 
        'assignment_form': assignment_form, 
        'user_to_edit': user_to_edit, 
        'current_assignments': current_assignments,
        'all_warehouses': all_warehouses,
        'all_roles': all_roles, 
        'users_list': user_list,
        'query': query or '',
        'active_assignment': getattr(request, 'active_assignment', None)
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
    'ready_to_ship'. This is where the [CS] button will be.
    """
    active_assignment = request.active_assignment
    active_role_name = getattr(active_assignment.role, 'name', None)

    # PERMISSION for [CS] button
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
        'can_take_action': can_take_action, # Pass permission to template
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