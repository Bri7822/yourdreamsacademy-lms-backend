# Create a new management command: management/commands/test_paypal_flow.py
from django.core.management.base import BaseCommand
from django.test.client import RequestFactory
from admin_dashboard.views import CreatePaymentView, CapturePaymentView
import json

class Command(BaseCommand):
    help = 'Test complete PayPal flow'
    
    def handle(self, *args, **options):
        # First, generate test users and courses if needed
        from accounts.models import UserProfile, Course
        
        # Create or get test data
        student = UserProfile.objects.filter(user_type='student').first()
        course = Course.objects.first()
        
        if not student or not course:
            self.stdout.write("Please create test users and courses first")
            return
            
        # Test the flow
        factory = RequestFactory()
        
        # 1. Create payment
        create_data = {
            'course_id': course.id,
            'student_id': student.id,
            'country_code': 'ZA'
        }
        
        request = factory.post('/test/', data=json.dumps(create_data), 
                              content_type='application/json')
        request.user = student.user  # Mock authenticated user
        
        create_view = CreatePaymentView()
        response = create_view.post(request)
        
        if response.status_code == 200:
            result = json.loads(response.content)
            order_id = result.get('orderID')
            
            # 2. Simulate capture
            capture_data = {'orderID': order_id}
            capture_request = factory.post('/test/', data=json.dumps(capture_data),
                                         content_type='application/json')
            capture_request.user = student.user
            
            capture_view = CapturePaymentView()
            capture_response = capture_view.post(capture_request)
            
            self.stdout.write(f"Capture result: {capture_response.status_code}")
        else:
            self.stdout.write(f"Create failed: {response.status_code}")