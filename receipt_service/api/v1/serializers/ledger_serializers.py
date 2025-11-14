from rest_framework import serializers
from decimal import Decimal
from receipt_service.services.receipt_model_service import model_service
from ....utils.currency_utils import currency_manager
from .category_serializers import CategorySerializer
from datetime import timedelta


class LedgerEntrySerializer(serializers.ModelSerializer):
    """Basic ledger entry serializer for list views"""
    category = CategorySerializer(read_only=True)
    receipt_id = serializers.UUIDField(source='receipt.id', read_only=True)
    receipt_filename = serializers.CharField(source='receipt.original_filename', read_only=True)
    formatted_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = model_service.ledger_entry_model
        fields = [
            'id', 'receipt_id', 'receipt_filename', 'category', 'date', 
            'vendor', 'amount', 'formatted_amount', 'currency', 'description', 
            'is_business_expense', 'is_reimbursable', 'created_at', 'updated_at'
        ]
    
    def get_formatted_amount(self, obj):
        """Get formatted amount with currency symbol"""
        return currency_manager.format_amount(obj.amount, obj.currency)


class LedgerEntryDetailSerializer(serializers.ModelSerializer):
    """Detailed ledger entry serializer"""
    category = CategorySerializer(read_only=True)
    receipt = serializers.SerializerMethodField()
    accuracy_metrics = serializers.SerializerMethodField()
    monthly_total = serializers.SerializerMethodField()
    category_total = serializers.SerializerMethodField()
    formatted_amount = serializers.SerializerMethodField()
    can_be_updated = serializers.SerializerMethodField()
    can_be_deleted = serializers.SerializerMethodField()
    
    class Meta:
        model = model_service.ledger_entry_model
        fields = [
            'id', 'receipt', 'category', 'date', 'vendor', 'amount', 'formatted_amount',
            'currency', 'description', 'tags', 'is_recurring', 'is_business_expense',
            'is_reimbursable', 'created_at', 'updated_at', 'accuracy_metrics',
            'monthly_total', 'category_total', 'can_be_updated', 'can_be_deleted'
        ]
    
    def get_receipt(self, obj):
        return {
            'id': str(obj.receipt.id),
            'original_filename': obj.receipt.original_filename,
            'status': obj.receipt.status,
            'upload_date': obj.receipt.created_at.isoformat(),
            'file_size_mb': round(obj.receipt.file_size / (1024 * 1024), 2)
        }
    
    def get_accuracy_metrics(self, obj):
        return {
            'was_ai_accurate': obj.was_ai_accurate,
            'accuracy_score': obj.accuracy_score,
            'user_corrections': {
                'amount': obj.user_corrected_amount,
                'category': obj.user_corrected_category,
                'vendor': obj.user_corrected_vendor,
                'date': obj.user_corrected_date
            }
        }
    
    def get_monthly_total(self, obj):
        return float(obj.get_monthly_total_for_user())
    
    def get_category_total(self, obj):
        return float(obj.get_category_total_for_user())
    
    def get_formatted_amount(self, obj):
        return currency_manager.format_amount(obj.amount, obj.currency)
    
    def get_can_be_updated(self, obj):
        """Check if entry can be updated (within 30 days)"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Allow updates within 30 days of creation
        update_deadline = obj.created_at + timedelta(days=30)
        return timezone.now() < update_deadline
    
    def get_can_be_deleted(self, obj):
        """Check if entry can be deleted (within 7 days and no dependencies)"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Allow deletion within 7 days of creation
        delete_deadline = obj.created_at + timedelta(days=7)
        return timezone.now() < delete_deadline

class LedgerEntryUpdateSerializer(serializers.Serializer):
    """Serializer for updating ledger entries - restricted fields only"""
    
    # Only allow specific fields to be updated
    category_id = serializers.UUIDField(required=False)
    vendor = serializers.CharField(max_length=255, allow_blank=True, required=False)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    is_business_expense = serializers.BooleanField(required=False)
    is_reimbursable = serializers.BooleanField(required=False)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50), 
        required=False, 
        allow_empty=True
    )
    
    def validate_category_id(self, value):
        """Validate category exists and is active"""
        if value:
            try:
                from receipt_service.services.receipt_model_service import model_service
                category = model_service.category_model.objects.get(
                    id=value, 
                    is_active=True
                )
                return value
            except model_service.category_model.DoesNotExist:
                raise serializers.ValidationError(
                    "Invalid or inactive category selected"
                )
        return value
    
    def validate_vendor(self, value):
        """Validate vendor name"""
        if value:
            value = value.strip()
            if len(value) > 255:
                raise serializers.ValidationError(
                    "Vendor name too long (max 255 characters)"
                )
            if any(char in value for char in ['<', '>', '"', "'"]):
                raise serializers.ValidationError(
                    "Vendor name contains invalid characters"
                )
        return value
    
    def validate_description(self, value):
        """Validate description"""
        if value:
            value = value.strip()
            if len(value) > 1000:
                raise serializers.ValidationError(
                    "Description too long (max 1000 characters)"
                )
        return value
    
    def validate_tags(self, value):
        """Validate tags"""
        if value:
            if len(value) > 10:
                raise serializers.ValidationError("Maximum 10 tags allowed")
            
            for tag in value:
                if len(tag.strip()) == 0:
                    raise serializers.ValidationError("Empty tags are not allowed")
                if len(tag.strip()) > 50:
                    raise serializers.ValidationError(
                        "Each tag must be 50 characters or less"
                    )
                if any(char in tag for char in ['<', '>', '"', "'"]):
                    raise serializers.ValidationError(
                        "Tags contain invalid characters"
                    )
        
        return [tag.strip() for tag in value] if value else []
    
    def update(self, instance, validated_data):
        """
        Update ledger entry instance
        This method is REQUIRED for serializers.Serializer
        """
        from receipt_service.services.receipt_model_service import model_service
        
        # Update category if provided
        if 'category_id' in validated_data:
            try:
                category = model_service.category_model.objects.get(
                    id=validated_data['category_id'],
                    is_active=True
                )
                instance.category = category
            except model_service.category_model.DoesNotExist:
                raise serializers.ValidationError(
                    {'category_id': 'Invalid or inactive category'}
                )
        
        # Update other fields
        for field in ['vendor', 'description', 'is_business_expense', 
                      'is_reimbursable', 'tags']:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        
        instance.save()
        return instance

class LedgerSummarySerializer(serializers.Serializer):
    """
    Serializer for ledger spending summary
    Uses Serializer (not ModelSerializer) since it's not a model
    """
    period = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_entries = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_total = serializers.CharField()
    business_expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_business = serializers.CharField()
    reimbursable_expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_reimbursable = serializers.CharField()
    base_currency = serializers.CharField()
    currencies_breakdown = serializers.DictField()



class QuotaStatusSerializer(serializers.Serializer):
    """Serializer for quota status information"""
    monthly_limit = serializers.IntegerField(read_only=True)
    current_month_uploads = serializers.IntegerField(read_only=True)
    remaining_uploads = serializers.IntegerField(read_only=True)
    reset_date = serializers.CharField(read_only=True)
    quota_exceeded = serializers.BooleanField(read_only=True)
    utilization_percentage = serializers.FloatField(read_only=True)