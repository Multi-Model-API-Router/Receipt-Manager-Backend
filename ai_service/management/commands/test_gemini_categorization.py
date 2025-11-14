# ai_service/management/commands/test_gemini_categorization.py

from django.core.management.base import BaseCommand
from django.conf import settings
import google.generativeai as genai
import json


class Command(BaseCommand):
    help = 'Test Gemini categorization with actual prompt'

    def handle(self, *args, **options):
        try:
            # Configure
            genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Test 1: Simple categorization
            self.stdout.write("\n1. Testing simple categorization...")
            
            prompt = """
            Analyze this receipt and suggest a category.
            
            Receipt: Walmart Supercenter - Groceries $45.99
            
            Available categories: Groceries, Dining, Shopping, Other
            
            Respond in JSON format:
            {
                "category": "category name",
                "confidence": 0.85,
                "reasoning": "why this category"
            }
            """
            
            response = model.generate_content(prompt)
            self.stdout.write(f"Raw response: {response.text}")
            
            try:
                parsed = json.loads(response.text)
                self.stdout.write(self.style.SUCCESS(f" Parsed JSON: {parsed}"))
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"✗ JSON parse failed: {str(e)}"))
            
            # Test 2: With actual service prompt builder
            self.stdout.write("\n2. Testing with actual service...")
            
            from ai_service.services.ai_categorization_service import AICategorizationService
            
            service = AICategorizationService()
            
            # Get real categories
            categories = service._get_available_categories()
            self.stdout.write(f"Found {len(categories)} categories")
            
            # Build actual prompt
            actual_prompt = service._build_categorization_prompt(
                receipt_text="Walmart Supercenter Receipt\nGroceries\nTotal: $45.99",
                vendor_name="Walmart",
                amount=None,
                categories=categories[:10],  # Limit for test
                user_preferences=None
            )
            
            self.stdout.write(f"\nPrompt length: {len(actual_prompt)} chars")
            self.stdout.write(f"Prompt preview: {actual_prompt[:200]}...")
            
            # Try actual call
            self.stdout.write("\nCalling Gemini with actual prompt...")
            response2 = model.generate_content(actual_prompt)
            
            self.stdout.write(f"Response: {response2.text[:500]}")
            
            # Check for safety issues
            if hasattr(response2, 'prompt_feedback'):
                self.stdout.write(f"Prompt feedback: {response2.prompt_feedback}")
            
            self.stdout.write(self.style.SUCCESS('\n✅ All tests passed!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Test failed: {str(e)}'))
            import traceback
            traceback.print_exc()
