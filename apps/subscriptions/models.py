"""
apps/subscriptions/models.py

Revenue / payments models.
Payment gateway (Paystack) will be wired in separately.
"""

from decimal import Decimal
from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    TRANSACTION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('ZAR', 'South African Rand'),
    ]

    GATEWAY_CHOICES = [
        ('paystack', 'Paystack'),
        ('manual', 'Manual'),
    ]

    transaction_id = models.CharField(max_length=50, unique=True)
    course = models.ForeignKey(
        'users.Course', on_delete=models.CASCADE, related_name='transactions'
    )
    student = models.ForeignKey(
        'users.UserProfile', on_delete=models.CASCADE, related_name='purchases'
    )
    teacher = models.ForeignKey(
        'users.UserProfile',
        on_delete=models.CASCADE,
        related_name='sales',
        null=True,
        blank=True,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')

    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    teacher_payout = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=TRANSACTION_STATUS_CHOICES, default='pending'
    )
    payment_gateway = models.CharField(max_length=50, choices=GATEWAY_CHOICES, default='paystack')
    gateway_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    is_sandbox = models.BooleanField(default=True)
    hosting_fee_applied = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'subscriptions'
        db_table = 'revenue_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_id} - {self.course.title}"

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            last = Transaction.objects.order_by('-id').first()
            last_id = last.id if last else 0
            self.transaction_id = f"TXN-{last_id + 1:04d}"

        # Revenue split: 70 % teacher / 30 % platform; 100 % platform for admin courses
        if self.teacher:
            self.platform_fee = self.amount * Decimal('0.3')
            self.teacher_payout = self.amount * Decimal('0.7')
        else:
            self.platform_fee = self.amount
            self.teacher_payout = Decimal('0.0')

        super().save(*args, **kwargs)


class TeacherPayout(models.Model):
    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    ]

    teacher = models.ForeignKey(
        'users.UserProfile', on_delete=models.CASCADE, related_name='payouts'
    )
    period_start = models.DateField()
    period_end = models.DateField()

    total_sales = models.DecimalField(max_digits=10, decimal_places=2)
    platform_commission = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2)

    hosting_fee = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)
    final_payout = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'subscriptions'
        db_table = 'revenue_teacherpayout'
        ordering = ['-period_end']

    def __str__(self):
        return f"Payout for {self.teacher.user.email} - {self.period_end}"

    def save(self, *args, **kwargs):
        self.final_payout = self.payout_amount - self.hosting_fee
        super().save(*args, **kwargs)


class RevenueReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()

    total_revenue = models.DecimalField(max_digits=15, decimal_places=2)
    total_transactions = models.IntegerField()
    average_transaction_value = models.DecimalField(max_digits=10, decimal_places=2)

    platform_commission = models.DecimalField(max_digits=15, decimal_places=2)
    teacher_payouts = models.DecimalField(max_digits=15, decimal_places=2)
    hosting_fees = models.DecimalField(max_digits=15, decimal_places=2)
    net_profit = models.DecimalField(max_digits=15, decimal_places=2)

    currency_breakdown = models.JSONField(default=dict)
    top_courses = models.JSONField(default=list)

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'subscriptions'
        db_table = 'revenue_report'
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.report_type.capitalize()} Report - {self.period_end}"