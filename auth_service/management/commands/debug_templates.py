# apps/auth_service/management/commands/debug_templates.py
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string, get_template
from django.template import TemplateDoesNotExist
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Debug email template loading'
    
    def handle(self, *args, **options):
        templates = [
            'emails/magic_link.html',
            'emails/email_verification.html', 
            'emails/welcome.html',
            'emails/password_reset.html'
        ]
        
        self.stdout.write("Template directories:")
        for template_dir in settings.TEMPLATES[0]['DIRS']:
            self.stdout.write(f"  - {template_dir}")
            if os.path.exists(template_dir):
                self.stdout.write(f"    ✅ Directory exists")
                # List contents
                try:
                    emails_dir = os.path.join(template_dir, 'emails')
                    if os.path.exists(emails_dir):
                        files = os.listdir(emails_dir)
                        self.stdout.write(f"    Files in emails/: {files}")
                    else:
                        self.stdout.write(f"    ❌ emails/ subdirectory not found")
                except Exception as e:
                    self.stdout.write(f"    Error listing files: {e}")
            else:
                self.stdout.write(f"    ❌ Directory does not exist")
        
        self.stdout.write("\nTesting template loading:")
        for template_name in templates:
            try:
                # Test template loading
                template = get_template(template_name)
                self.stdout.write(f"✅ {template_name} - Found")
                
                # Test rendering
                context = {
                    'user_name': 'Test User',
                    'magic_url': 'http://test.com/magic',
                    'verification_url': 'http://test.com/verify',
                    'reset_url': 'http://test.com/reset',
                    'frontend_url': 'http://test.com',
                    'email': 'test@example.com'
                }
                
                html = render_to_string(template_name, context)
                self.stdout.write(f"   Rendered length: {len(html)} characters")
                
            except TemplateDoesNotExist as e:
                self.stdout.write(f"❌ {template_name} - Not found")
                self.stdout.write(f"   Error: {str(e)}")
            except Exception as e:
                self.stdout.write(f"⚠️ {template_name} - Error: {str(e)}")
