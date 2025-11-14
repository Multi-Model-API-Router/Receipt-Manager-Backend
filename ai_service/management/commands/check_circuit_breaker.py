# ai_service/management/commands/check_circuit_breaker.py

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check circuit breaker state'

    def handle(self, *args, **options):
        from ai_service.services.ai_categorization_service import AICategorizationService
        
        service = AICategorizationService()
        cb = service.circuit_breaker
        
        self.stdout.write(f"Circuit Breaker: {cb.name}")
        self.stdout.write(f"State: {cb.state}")
        self.stdout.write(f"Failure count: {cb.failure_count}")
        
        if cb.state.name == 'OPEN':
            self.stdout.write(self.style.WARNING(
                "\n⚠ Circuit breaker is OPEN - service unavailable"
            ))
            self.stdout.write("Run 'python manage.py reset_circuit_breaker' to reset")
        elif cb.state.name == 'CLOSED':
            self.stdout.write(self.style.SUCCESS(
                "\n Circuit breaker is CLOSED - service available"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\n⚡ Circuit breaker is HALF-OPEN - testing recovery"
            ))
