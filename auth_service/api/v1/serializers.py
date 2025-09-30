from rest_framework import serializers
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password

from ...services.auth_model_service import model_service

class RequestMagicLinkSerializer(serializers.Serializer):
    """Serializer for magic link request"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Validate email format"""
        try:
            validate_email(value)
        except Exception as e:
            raise serializers.ValidationError("Invalid email format")
        
        return value.lower().strip()

class MagicLinkLoginSerializer(serializers.Serializer):
    """Serializer for magic link login"""
    token = serializers.CharField(max_length=255)
    
    def validate_token(self, value):
        """Validate token format"""
        if not value or len(value) < 10:
            raise serializers.ValidationError("Invalid token format")
        return value.strip()

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile data"""
    
    class Meta:
        model = model_service.user_model
        fields = [
            'id', 'email', 'first_name', 'last_name', 
            'is_email_verified', 'monthly_upload_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'monthly_upload_count', 'created_at', 'updated_at']
    
    def validate_email(self, value):
        """Validate email uniqueness"""
        User = model_service.user_model
        
        if self.instance:
            # Update case - exclude current user
            if User.objects.filter(email=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Email address already in use")
        else:
            # Create case
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email address already in use")
        
        return value.lower().strip()

class UpdateEmailSerializer(serializers.Serializer):
    """Serializer for email update"""
    new_email = serializers.EmailField()
    
    def validate_new_email(self, value):
        """Validate new email"""
        User = model_service.user_model
        
        # Check if email already exists
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email address already in use")
        
        return value.lower().strip()

class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification"""
    token = serializers.CharField(max_length=255)
    
    def validate_token(self, value):
        """Validate verification token"""
        if not value or len(value) < 10:
            raise serializers.ValidationError("Invalid verification token")
        return value.strip()

class RefreshTokenSerializer(serializers.Serializer):
    """Serializer for token refresh"""
    refresh = serializers.CharField()
    
    def validate_refresh(self, value):
        """Validate refresh token format"""
        if not value:
            raise serializers.ValidationError("Refresh token is required")
        return value.strip()

class UserRegistrationSerializer(serializers.Serializer):
    """Serializer for user registration (optional password-based)"""
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False)
    
    def validate_email(self, value):
        """Validate email uniqueness"""
        User = model_service.user_model
        
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email address already registered")
        
        return value.lower().strip()
    
    def validate_password(self, value):
        """Validate password strength"""
        if value:
            try:
                validate_password(value)
            except Exception as e:
                raise serializers.ValidationError(str(e))
        return value
    
    def create(self, validated_data):
        """Create new user"""
        User = model_service.user_model
        
        password = validated_data.pop('password', None)
        user = User.objects.create_user(**validated_data)
        
        if password:
            user.set_password(password)
            user.save()
        
        return user
