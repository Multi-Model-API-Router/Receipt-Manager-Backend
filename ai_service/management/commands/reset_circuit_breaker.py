# ai_service/management/commands/reset_circuit_breaker.py

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Reset circuit breaker state'

    def handle(self, *args, **options):
        from ai_service.services.ai_categorization_service import AICategorizationService
        
        service = AICategorizationService()
        cb = service.circuit_breaker
        
        self.stdout.write(f"Before: {cb.state.name} (failures: {cb.failure_count})")
        
        cb.reset()
        
        self.stdout.write(self.style.SUCCESS(
            f"After: {cb.state.name} (failures: {cb.failure_count})"
        ))
        self.stdout.write(self.style.SUCCESS('\n✅ Circuit breaker reset!'))
