from rest_framework import serializers
from ....services.receipt_model_service import model_service


class CategorySerializer(serializers.ModelSerializer):
    """Basic category serializer"""
    
    class Meta:
        model = model_service.category_model
        fields = [
            'id', 'name', 'slug', 'icon', 'color', 
            'is_active', 'display_order'
        ]
        read_only_fields = ['id', 'slug', 'is_active', 'display_order']  # These shouldn't be modified by users


class CategoryStatisticsSerializer(serializers.Serializer):
    """Serializer for category usage statistics"""
    category = CategorySerializer(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    entry_count = serializers.IntegerField(read_only=True)
    percentage = serializers.FloatField(read_only=True)
    average_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class CategoryPreferenceSerializer(serializers.Serializer):
    """Serializer for user category preferences"""
    category = CategorySerializer(read_only=True)
    usage_count = serializers.IntegerField(read_only=True)
    last_used = serializers.DateTimeField(read_only=True, allow_null=True)


class CategorySuggestionSerializer(serializers.Serializer):
    """Serializer for AI category suggestions"""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    confidence = serializers.FloatField(read_only=True, min_value=0.0, max_value=1.0)
    reason = serializers.CharField(read_only=True)


class CategoryValidationSerializer(serializers.Serializer):
    """Serializer for category validation requests"""
    category_id = serializers.UUIDField(required=True)
    
    def validate_category_id(self, value):
        """Validate that the category exists and is active"""
        from ....services.receipt_import_service import service_import
        
        try:
            category_service = service_import.category_service
            category_service.get_category_by_id(str(value), check_active=True)
            return value
        except Exception:
            raise serializers.ValidationError("Invalid or inactive category")
