# management/commands/simulate_transactions.py
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from your_app.views import CreatePaymentView, CapturePaymentView
import json

class Command(BaseCommand):
    help = 'Simulate transactions for testing revenue logic'
    
    def add_arguments(self, parser):
        parser.add_argument('--country', type=str, default='ZA', help='Country code for currency testing')
        parser.add_argument('--course', type=int, required=True, help='Course ID')
        parser.add_argument('--student', type=int, required=True, help='Student Profile ID')
    
    def handle(self, *args, **options):
        factory = RequestFactory()
        
        # Create mock request with Cloudflare header
        create_data = json.dumps({
            'course_id': options['course'],
            'student_id': options['student']
        })
        
        request = factory.post('/api/paypal/create-payment/', 
                              data=create_data,
                              content_type='application/json')
        request.META['HTTP_CF_IPCOUNTRY'] = options['country']
        
        # Create payment
        view = CreatePaymentView()
        response = view.post(request)
        result = json.loads(response.content)
        
        if 'orderID' in result:
            self.stdout.write(f"Created order: {result['orderID']}")
            
            # Now capture (in a real scenario, this would be after user approval)
            capture_data = json.dumps({'orderID': result['orderID']})
            capture_request = factory.post('/api/paypal/capture-payment/', 
                                         data=capture_data,
                                         content_type='application/json')
            
            capture_response = view.post(capture_request)
            capture_result = json.loads(capture_response.content)
            
            self.stdout.write(f"Capture result: {capture_result}")
        else:
            self.stdout.write(f"Error: {result}")