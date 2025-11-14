# shared/management/commands/clear_all_data.py

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.apps import apps
from django.conf import settings
import os
import glob
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clear all data from database and log files'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )
        parser.add_argument(
            '--keep-users',
            action='store_true',
            help='Keep superuser accounts',
        )
        parser.add_argument(
            '--clear-logs',
            action='store_true',
            help='Also clear all log files',
        )
        parser.add_argument(
            '--logs-only',
            action='store_true',
            help='Only clear log files (skip database)',
        )
    
    def handle(self, *args, **options):
        """Clear data and optionally log files"""
        
        # Confirmation
        if not options['force']:
            warning_msg = '\n⚠️  This will:'
            
            if not options['logs_only']:
                warning_msg += '\n  - DELETE ALL DATA from database tables'
            
            if options['clear_logs'] or options['logs_only']:
                warning_msg += '\n  - CLEAR ALL LOG FILES'
            
            warning_msg += '\n\n⚠️  This action cannot be undone!'
            
            self.stdout.write(self.style.WARNING(warning_msg))
            
            if options['keep_users']:
                self.stdout.write(
                    self.style.NOTICE('\n✓ Superuser accounts will be preserved.')
                )
            
            confirm = input('\nType "YES DELETE ALL" to confirm: ')
            
            if confirm != 'YES DELETE ALL':
                self.stdout.write(self.style.ERROR('\n❌ Aborted.\n'))
                return
        
        # Clear database data
        if not options['logs_only']:
            self._clear_database(options['keep_users'])
        
        # Clear log files
        if options['clear_logs'] or options['logs_only']:
            self._clear_logs()
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ All operations completed successfully!\n')
        )
    
    def _clear_database(self, keep_users=False):
        """Clear all database data"""
        self.stdout.write('\n🗑️  Clearing database data...\n')
        
        try:
            with transaction.atomic():
                deletion_order = self._get_deletion_order()
                total_deleted = 0
                
                for model in deletion_order:
                    table_name = model._meta.db_table
                    
                    # Special handling for User model
                    if keep_users and model._meta.label == 'auth_service.User':
                        count = model.objects.filter(is_superuser=False).count()
                        if count > 0:
                            model.objects.filter(is_superuser=False).delete()
                            total_deleted += count
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Deleted {count} non-superuser records from {table_name}'
                                )
                            )
                        continue
                    
                    # Delete all records
                    count = model.objects.count()
                    if count > 0:
                        model.objects.all().delete()
                        total_deleted += count
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✓ Deleted {count} records from {table_name}'
                            )
                        )
                
                # Reset sequences
                self._reset_sequences()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Database: Deleted {total_deleted} records'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Database error: {str(e)}\n')
            )
            logger.error(f'Database deletion failed: {str(e)}', exc_info=True)
            raise
    
    def _clear_logs(self):
        """Clear all log files"""
        self.stdout.write('\n🗑️  Clearing log files...\n')
        
        try:
            log_files_cleared = 0
            total_size_cleared = 0
            
            # Get log directories from settings
            log_dirs = self._get_log_directories()
            
            for log_dir in log_dirs:
                if not os.path.exists(log_dir):
                    self.stdout.write(
                        self.style.NOTICE(f'  Log directory not found: {log_dir}')
                    )
                    continue
                
                # Find all log files
                log_patterns = ['*.log', '*.log.*', '*.out', '*.err']
                
                for pattern in log_patterns:
                    log_files = glob.glob(os.path.join(log_dir, pattern))
                    
                    for log_file in log_files:
                        try:
                            # Get file size before clearing
                            file_size = os.path.getsize(log_file)
                            
                            # Clear file content (keep file for logger handles)
                            with open(log_file, 'w') as f:
                                f.write('')
                            
                            log_files_cleared += 1
                            total_size_cleared += file_size
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Cleared {os.path.basename(log_file)} '
                                    f'({self._format_size(file_size)})'
                                )
                            )
                            
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  Could not clear {os.path.basename(log_file)}: {str(e)}'
                                )
                            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Logs: Cleared {log_files_cleared} files '
                    f'({self._format_size(total_size_cleared)} total)'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Log clearing error: {str(e)}\n')
            )
            logger.error(f'Log clearing failed: {str(e)}', exc_info=True)
    
    def _get_log_directories(self):
        """Get all log directories from settings"""
        log_dirs = set()
        
        # Check LOGGING configuration
        if hasattr(settings, 'LOGGING'):
            logging_config = settings.LOGGING
            
            # Extract file paths from handlers
            if 'handlers' in logging_config:
                for handler_name, handler_config in logging_config['handlers'].items():
                    if 'filename' in handler_config:
                        log_file = handler_config['filename']
                        log_dir = os.path.dirname(log_file)
                        if log_dir:
                            log_dirs.add(log_dir)
        
        # Common log directory locations
        base_dir = settings.BASE_DIR
        common_dirs = [
            os.path.join(base_dir, 'logs'),
            os.path.join(base_dir, 'log'),
            os.path.join(base_dir, 'var', 'log'),
            os.path.join(base_dir, 'tmp', 'logs'),
        ]
        
        for common_dir in common_dirs:
            if os.path.exists(common_dir):
                log_dirs.add(common_dir)
        
        return list(log_dirs)
    
    def _format_size(self, bytes_size):
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    def _get_deletion_order(self):
        """Get models in correct deletion order"""
        services = ['auth_service', 'receipt_service', 'ai_service']
        all_models = []
        
        for service in services:
            try:
                app_config = apps.get_app_config(service)
                all_models.extend(app_config.get_models())
            except LookupError:
                pass
        
        ordered_models = []
        model_map = {model._meta.db_table: model for model in all_models}
        
        deletion_sequence = [
            'ai_extracted_data',
            'ai_category_predictions',
            'ai_ocr_results',
            'ai_processing_jobs',
            'receipt_ledger_entries',
            'receipt_user_category_preferences',
            'receipts',
            'receipt_categories',
            'auth_token_blacklist',
            'auth_login_attempts',
            'auth_email_verifications',
            'auth_magic_links',
            'auth_users',
        ]
        
        for table_name in deletion_sequence:
            if table_name in model_map:
                ordered_models.append(model_map[table_name])
        
        for model in all_models:
            if model not in ordered_models:
                ordered_models.append(model)
        
        return ordered_models
    
    def _reset_sequences(self):
        """Reset auto-increment sequences"""
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT 'SELECT SETVAL(' ||
                           quote_literal(quote_ident(sequence_namespace.nspname) || '.' || quote_ident(class_sequence.relname)) ||
                           ', 1, false);'
                    FROM pg_class AS class_sequence
                    JOIN pg_namespace AS sequence_namespace ON class_sequence.relnamespace = sequence_namespace.oid
                    WHERE class_sequence.relkind = 'S';
                """)
                
                reset_queries = cursor.fetchall()
                for query in reset_queries:
                    try:
                        cursor.execute(query[0])
                    except Exception:
                        pass
                
            elif connection.vendor == 'sqlite':
                cursor.execute("DELETE FROM sqlite_sequence;")
                
            elif connection.vendor == 'mysql':
                cursor.execute("""
                    SELECT CONCAT('ALTER TABLE `', table_name, '` AUTO_INCREMENT = 1;')
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    AND auto_increment IS NOT NULL;
                """)
                
                reset_queries = cursor.fetchall()
                for query in reset_queries:
                    try:
                        cursor.execute(query[0])
                    except Exception:
                        pass
