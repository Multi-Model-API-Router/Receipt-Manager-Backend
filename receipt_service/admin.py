# receipt_service/admin.py

from django.contrib import admin
from .models import Receipt, Category, LedgerEntry

# Simple registrations for debugging only
admin.site.register(Receipt)
admin.site.register(Category)
admin.site.register(LedgerEntry)

# Optional: Customize site header
admin.site.site_header = 'Receipt Manager Admin'
