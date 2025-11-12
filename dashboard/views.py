from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html')

def ready_to_ship(request):
    return render(request,'dashboard/ready_to_ship.html')

def total_shipment_view(request):
    return render(request, 'dashboard/total_shipment.html')

def supplier_to_warehouse(request):
    return render(request, 'dashboard/supplier_to_warehouse.html')

def create_warehouse_view(request):
    return render(request,'dashboard/create_warehouse.html')

# dashboard/views.py (add this function)

def asin_upc_view(request):
    """View for the ASIN/UPC management page."""
    context = {
        'page_title': 'ASIN/UPC (Total: 0)',
    }
    return render(request, 'dashboard/asin_upc.html', context)

def create_user_view(request):
    """View for the user creation and management page."""
    context = {
        'page_title': 'Users (Total: 0)',
    }
    return render(request, 'dashboard/create_user.html', context)

def store_management_view (request):
    """View for the user creation and management page."""
    context = {
        'page_title': 'Stores (Total: 0)',
    }
    return render(request, 'dashboard/store_management.html', context)

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'dashboard/login.html', {'error': 'Invalid username or password'})
    return render(request, 'dashboard/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html', {'user': request.user})

