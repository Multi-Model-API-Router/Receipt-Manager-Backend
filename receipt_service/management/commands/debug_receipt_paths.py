# management/commands/debug_receipt_paths.py

from django.core.management.base import BaseCommand
from receipt_service.models import Receipt
import os
from django.conf import settings


class Command(BaseCommand):
    help = 'Debug receipt file paths'

    def handle(self, *args, **options):
        receipts = Receipt.objects.order_by('-created_at')[:5]
        
        self.stdout.write(self.style.WARNING(f"MEDIA_ROOT: {settings.MEDIA_ROOT}"))
        self.stdout.write(self.style.WARNING(f"MEDIA_URL: {settings.MEDIA_URL}"))
        self.stdout.write("")
        
        for receipt in receipts:
            self.stdout.write(f"Receipt ID: {receipt.id}")
            self.stdout.write(f"  file_path: {receipt.file_path}")
            self.stdout.write(f"  file_path.name: {receipt.file_path.name if receipt.file_path else 'None'}")
            
            if receipt.file_path:
                # Check different possible paths
                paths_to_check = [
                    receipt.file_path.name,
                    receipt.file_path.path,
                    os.path.join(settings.MEDIA_ROOT, receipt.file_path.name),
                    os.path.join(settings.MEDIA_ROOT, 'receipts', receipt.file_path.name),
                ]
                
                self.stdout.write("  Checking paths:")
                for path in paths_to_check:
                    exists = os.path.exists(path) if path else False
                    status = "EXISTS" if exists else "NOT FOUND"
                    self.stdout.write(f"    {status}: {path}")
            
            self.stdout.write("")
