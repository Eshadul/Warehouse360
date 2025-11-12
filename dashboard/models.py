from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('warehouse_admin', 'Warehouse Admin'),
        ('store_manager', 'Store Manager'),
        ('warehouse_manager', 'Warehouse Manager'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='store_manager')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

