# subscriptions serializers
from rest_framework import serializers
from .models import Transaction, TeacherPayout, RevenueReport


class TransactionSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    teacher_name = serializers.CharField(
        source='teacher.user.get_full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'course', 'course_title',
            'student', 'student_name', 'teacher', 'teacher_name',
            'amount', 'currency', 'platform_fee', 'teacher_payout',
            'status', 'payment_gateway', 'gateway_transaction_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['transaction_id', 'platform_fee', 'teacher_payout']


class TeacherPayoutSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True)
    teacher_email = serializers.CharField(source='teacher.user.email', read_only=True)

    class Meta:
        model = TeacherPayout
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_email',
            'period_start', 'period_end', 'total_sales',
            'platform_commission', 'payout_amount', 'hosting_fee',
            'final_payout', 'status', 'processed_at',
            'created_at', 'updated_at',
        ]


class RevenueReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueReport
        fields = [
            'id', 'report_type', 'period_start', 'period_end',
            'total_revenue', 'total_transactions', 'average_transaction_value',
            'platform_commission', 'teacher_payouts', 'hosting_fees',
            'net_profit', 'currency_breakdown', 'top_courses',
            'generated_at',
        ]