from django.shortcuts import render

# Create your views here.
from django.db.models import Sum
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import Transaction, TeacherPayout, RevenueReport
from .serializers import TransactionSerializer, TeacherPayoutSerializer, RevenueReportSerializer
from apps.users.models import UserProfile


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related(
        'course', 'student__user', 'teacher__user'
    ).all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminUser]

    def list(self, request, *args, **kwargs):
        ordering = request.query_params.get('ordering', '-created_at')
        queryset = self.get_queryset().order_by(ordering)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def process_refund(self, request, pk=None):
        transaction = self.get_object()
        if transaction.status != 'completed':
            return Response(
                {'error': 'Only completed transactions can be refunded'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transaction.status = 'refunded'
        transaction.save()
        return Response({'status': 'refunded'})


class TeacherPayoutViewSet(viewsets.ModelViewSet):
    queryset = TeacherPayout.objects.select_related('teacher__user').all()
    serializer_class = TeacherPayoutSerializer
    permission_classes = [IsAdminUser]

    @action(detail=True, methods=['post'])
    def process_payout(self, request, pk=None):
        payout = self.get_object()
        if payout.status != 'pending':
            return Response(
                {'error': 'Only pending payouts can be processed'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payout.status = 'processed'
        payout.processed_at = timezone.now()
        payout.save()
        return Response({'status': 'payout processed'})


class RevenueReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RevenueReport.objects.all()
    serializer_class = RevenueReportSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        total_revenue = (
            Transaction.objects.filter(status='completed')
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        platform_commission = (
            Transaction.objects.filter(status='completed')
            .aggregate(total=Sum('platform_fee'))['total'] or 0
        )
        teacher_payouts = (
            Transaction.objects.filter(status='completed', teacher__isnull=False)
            .aggregate(total=Sum('teacher_payout'))['total'] or 0
        )
        active_teachers = (
            UserProfile.objects.filter(
                user_type='teacher',
                courses_taught__isnull=False,
                sales__isnull=False,
            )
            .distinct()
            .count()
        )
        hosting_fees = active_teachers * 200  # R200 per teacher per month

        return Response({
            'total_revenue': total_revenue,
            'platform_commission': platform_commission,
            'teacher_payouts': teacher_payouts,
            'hosting_fees': hosting_fees,
            'active_teachers': active_teachers,
        })