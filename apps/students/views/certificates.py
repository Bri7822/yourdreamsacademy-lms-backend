import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.students.compat import Lesson, Enrollment
from apps.students.compat import Course
from apps.students.models import StudentExercise, Certificate
from apps.students.serializers import CertificateSerializer

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([])
def student_certificates_list(request):
    """
    All users (including guests) can see courses with certificate status.
    Authenticated users see their real progress.
    """
    user = request.user
    try:
        all_courses = Course.objects.filter(is_active=True).order_by('title')
        certificates_data = []

        for course in all_courses:
            try:
                base = {
                    'id': course.id,
                    'course_title': course.title,
                    'course_code': course.code,
                    'category': course.category,
                    'teacher_name': getattr(course, 'teacher_name', None),
                    'total_lessons': course.lessons.filter(is_active=True).count(),
                    'description': course.description,
                }

                if user.is_authenticated:
                    total = Lesson.objects.filter(course=course, is_active=True).count()
                    completed = StudentExercise.objects.filter(
                        student=user, lesson__course=course, completed=True
                    ).count()
                    progress = round((completed / total) * 100, 1) if total else 0
                    is_completed = progress >= 100
                    is_enrolled = Enrollment.objects.filter(
                        student=user, course=course, status__in=['approved', 'completed']
                    ).exists()

                    existing_cert = Certificate.objects.filter(user=user, course=course, is_active=True).first()

                    if existing_cert:
                        cert_data = {
                            **base,
                            'certificate_id': str(existing_cert.certificate_id),
                            'issue_date': existing_cert.issued_date.strftime('%B %d, %Y'),
                            'formatted_grade': f"{existing_cert.grade}%",
                            'download_url': existing_cert.download_url,
                            'is_valid': existing_cert.is_valid,
                            'accessible': existing_cert.is_valid,
                            'message': 'Certificate available for download' if existing_cert.is_valid else 'Complete the course to access this certificate',
                            'progress': progress,
                            'is_enrolled': is_enrolled,
                            'is_real_certificate': True,
                        }
                    else:
                        cert_data = {
                            **base,
                            'certificate_id': f'course-{course.code}-{user.id}',
                            'issue_date': 'In Progress' if not is_completed else timezone.now().strftime('%B %d, %Y'),
                            'formatted_grade': f'{progress}%',
                            'download_url': f'/api/student/courses/{course.code}/generate-certificate/' if is_completed else None,
                            'is_valid': is_completed,
                            'accessible': is_completed and is_enrolled,
                            'message': (
                                'Course completed! Click to generate certificate.' if is_completed
                                else f'Progress: {progress}% - Complete all lessons to earn certificate' if is_enrolled
                                else 'Enroll in this course to earn a certificate'
                            ),
                            'progress': progress,
                            'is_enrolled': is_enrolled,
                            'is_real_certificate': False,
                        }
                else:
                    cert_data = {
                        **base,
                        'certificate_id': f'guest-{course.code}',
                        'issue_date': 'Available upon completion',
                        'formatted_grade': '0%',
                        'download_url': None,
                        'is_valid': False,
                        'accessible': False,
                        'message': 'Sign up and complete this course to earn a certificate',
                        'progress': 0,
                        'is_enrolled': False,
                        'is_real_certificate': False,
                    }

                certificates_data.append(cert_data)
            except Exception as e:
                logger.warning("Error processing certificate for course %s: %s", course.code, e)
                continue

        return Response({
            'certificates': certificates_data,
            'total_certificates': len(certificates_data),
            'user_type': 'authenticated' if user.is_authenticated else 'guest',
            'total_courses': all_courses.count(),
        })

    except Exception as e:
        logger.exception("student_certificates_list error")
        return Response(
            {'detail': 'Failed to load certificates.', 'certificates': [], 'total_certificates': 0},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_certificate(request, certificate_id):
    user = request.user
    try:
        certificate = get_object_or_404(Certificate, certificate_id=certificate_id, user=user, is_active=True)
        if not certificate.is_valid:
            return Response({'detail': 'Course not completed.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            'detail': 'Certificate download started!',
            'download_url': certificate.download_url or certificate.generate_certificate(),
            'certificate_id': str(certificate.certificate_id),
            'course_title': certificate.course.title,
            'issued_date': certificate.issued_date.strftime('%B %d, %Y'),
        })
    except Exception as e:
        logger.exception("download_certificate error")
        return Response({'detail': 'Failed to download certificate.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def view_certificate(request, certificate_id):
    user = request.user
    try:
        certificate = get_object_or_404(Certificate, certificate_id=certificate_id, user=user, is_active=True)
        if not certificate.is_valid:
            return Response({'detail': 'Certificate not available.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = CertificateSerializer(certificate, context={'request': request})
        return Response({
            **serializer.data,
            'viewable': True,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.email,
        })
    except Exception as e:
        logger.exception("view_certificate error")
        return Response({'detail': 'Certificate not found.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_certificate(request, course_code):
    user = request.user
    course = get_object_or_404(Course, code=course_code, is_active=True)
    try:
        enrollment = Enrollment.objects.filter(student=user, course=course, status='completed').first()
        if not enrollment:
            return Response({'detail': 'Course not completed.'}, status=status.HTTP_400_BAD_REQUEST)

        total = Lesson.objects.filter(course=course, is_active=True).count()
        completed = StudentExercise.objects.filter(student=user, lesson__course=course, completed=True).count()
        if completed < total:
            return Response({'detail': 'Not all lessons completed.'}, status=status.HTTP_400_BAD_REQUEST)

        scores = list(StudentExercise.objects.filter(
            student=user, lesson__course=course, completed=True
        ).values_list('score', flat=True))
        avg_grade = (sum(scores) / len(scores) * 100) if scores else 100.0

        certificate, created = Certificate.objects.get_or_create(
            user=user, course=course, defaults={'grade': avg_grade}
        )
        if not created:
            certificate.grade = avg_grade
            certificate.save()

        if not certificate.download_url:
            certificate.download_url = certificate.generate_certificate()
            certificate.save()

        serializer = CertificateSerializer(certificate, context={'request': request})
        return Response(
            {'detail': 'Certificate generated.' if created else 'Certificate updated.', 'certificate': serializer.data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
    except Exception as e:
        logger.exception("generate_certificate error for %s", course_code)
        return Response({'detail': 'Failed to generate certificate.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_certificate_eligibility(request, course_code):
    user = request.user
    course = get_object_or_404(Course, code=course_code, is_active=True)
    try:
        enrollment = Enrollment.objects.filter(student=user, course=course).first()
        if not enrollment or enrollment.status != 'completed':
            return Response({'eligible': False, 'reason': 'Course not completed', 'progress': 0})

        total = Lesson.objects.filter(course=course, is_active=True).count()
        completed = StudentExercise.objects.filter(student=user, lesson__course=course, completed=True).count()
        progress = round((completed / total * 100), 1) if total else 0
        eligible = completed >= total

        existing = Certificate.objects.filter(user=user, course=course).first()
        return Response({
            'eligible': eligible,
            'progress': progress,
            'completed_lessons': completed,
            'total_lessons': total,
            'has_certificate': existing is not None,
            'certificate': CertificateSerializer(existing, context={'request': request}).data if existing else None,
        })
    except Exception as e:
        logger.exception("check_certificate_eligibility error for %s", course_code)
        return Response({'eligible': False, 'reason': 'Error checking eligibility'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
