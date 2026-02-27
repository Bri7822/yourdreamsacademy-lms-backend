# accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import CustomUser, UserProfile

# accounts/serializers.py
class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'is_active', 'date_joined', 'profile']
    
    def get_profile(self, obj):
        try:
            profile = obj.profile
            return {
                'user_type': profile.user_type,
                'terms_agreed': profile.terms_agreed,
                # Include other profile fields as needed
            }
        except UserProfile.DoesNotExist:
            return None
         
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    user_type = serializers.CharField(required=True)  # Add this field
    terms_agreed = serializers.BooleanField(required=True)  # Add this field
    
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'password', 'password2', 'user_type', 'terms_agreed')
        
    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        if len(data['password']) < 8:
            raise serializers.ValidationError({"password": "Password must be at least 8 characters long."})
            
        if not data['terms_agreed']:
            raise serializers.ValidationError({"terms_agreed": "You must agree to the terms and conditions."})
            
        return data
        
    def create(self, validated_data):
        # Remove fields not in User model before creating instance
        validated_data.pop('password2')
        user_type = validated_data.pop('user_type')  # Store but remove from validated_data
        validated_data.pop('terms_agreed')  # Remove as it's not stored in User model
        
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password']
        )
        
        # Handle user_type separately - you might want to store this in a profile model
        # or add it to your CustomUser model if needed
        # Example: user.profile.user_type = user_type
        
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, style={'input_type': 'password'})
    
    def validate(self, data):
        user = authenticate(request=self.context.get('request'),
                           username=data.get('email'),
                           password=data.get('password'))
        if not user:
            raise serializers.ValidationError('Invalid login credentials')
        
        # Check if user email is verified
        if not user.is_active:
            raise serializers.ValidationError('Please verify your email before logging in')
            
        data['user'] = user
        return data