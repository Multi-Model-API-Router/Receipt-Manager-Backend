# ai_service/management/commands/check_gemini_models.py

from django.core.management.base import BaseCommand
import google.generativeai as genai
from django.conf import settings


class Command(BaseCommand):
    help = 'List available Gemini models'

    def handle(self, *args, **options):
        try:
            genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
            
            self.stdout.write(self.style.SUCCESS('Available Gemini models:'))
            
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    self.stdout.write(f"   {model.name}")
                    self.stdout.write(f"    Display name: {model.display_name}")
                    self.stdout.write(f"    Description: {model.description}")
                    self.stdout.write("")
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to list models: {str(e)}')
            )
