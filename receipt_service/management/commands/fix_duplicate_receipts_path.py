# management/commands/fix_duplicate_receipts_path.py

from django.core.management.base import BaseCommand
from receipt_service.models import Receipt
import os
import shutil


class Command(BaseCommand):
    help = 'Fix duplicate receipts path'

    def handle(self, *args, **options):
        from django.conf import settings
        
        receipts = Receipt.objects.all()
        fixed_count = 0
        
        for receipt in receipts:
            if not receipt.file_path or not receipt.file_path.name:
                continue
            
            old_path = receipt.file_path.name
            
            # Check if path has duplicate "receipts"
            if old_path.startswith('receipts/receipts/'):
                # Remove duplicate
                new_path = old_path.replace('receipts/receipts/', 'receipts/', 1)
                
                # Get full paths
                old_full_path = os.path.join(settings.MEDIA_ROOT, old_path)
                new_full_path = os.path.join(settings.MEDIA_ROOT, new_path)
                
                # Check if old file exists
                if os.path.exists(old_full_path):
                    # Create new directory if needed
                    os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
                    
                    # Move file
                    shutil.move(old_full_path, new_full_path)
                    
                    # Update database
                    receipt.file_path = new_path
                    receipt.save(update_fields=['file_path'])
                    
                    fixed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Fixed: {old_path} -> {new_path}')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f'Fixed {fixed_count} receipts')
        )
