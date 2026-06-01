# core/errors.py
from rest_framework import status
from rest_framework.exceptions import APIException


class SubscriptionRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'A paid subscription is required to access this feature.'
    default_code = 'subscription_required'


class AlreadySubscribed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'User already has an active subscription.'
    default_code = 'already_subscribed'


class GradeMismatch(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'You can only access content for your registered grade.'
    default_code = 'grade_mismatch'


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Please verify your email address before continuing.'
    default_code = 'email_not_verified'