# apps/subscriptions/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path(
        'revenue/transactions/',
        views.TransactionViewSet.as_view({'get': 'list'}),
        name='revenue-transactions',
    ),
    path(
        'revenue/transactions/<int:pk>/process_refund/',
        views.TransactionViewSet.as_view({'post': 'process_refund'}),
        name='process-refund',
    ),
    path(
        'revenue/summary/',
        views.RevenueReportViewSet.as_view({'get': 'summary'}),
        name='revenue-summary',
    ),
]