# apps/users/apps.py
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    label = 'users'

    def ready(self):
        from django.db.models.signals import post_save
        from django.apps import apps as django_apps
        from django.utils import timezone
        import logging

        logger = logging.getLogger(__name__)

        def auto_complete_enrollment(sender, instance, **kwargs):
            """
            Whenever a StudentExercise is marked completed, check whether
            the student's enrollment in that course has now hit 100%
            progress. If so, mark the enrollment as completed.
            """
            if not instance.completed:
                return

            Enrollment = django_apps.get_model('users', 'Enrollment')

            try:
                enrollment = Enrollment.objects.get(
                    student=instance.student,
                    course=instance.lesson.course,
                )
            except Enrollment.DoesNotExist:
                return

            if enrollment.status == Enrollment.APPROVED and enrollment.progress >= 100:
                enrollment.status = Enrollment.COMPLETED
                enrollment.completed_at = timezone.now()
                enrollment.save(update_fields=['status', 'completed_at'])
                logger.info(
                    f"Auto-completed enrollment {enrollment.id} "
                    f"({enrollment.student.email} → {enrollment.course.title})"
                )

        try:
            StudentExercise = django_apps.get_model('students', 'StudentExercise')
            post_save.connect(
                auto_complete_enrollment,
                sender=StudentExercise,
                weak=False,
                dispatch_uid='auto_complete_enrollment_on_progress',
            )
        except LookupError:
            logger.warning(
                "Could not register auto-complete signal: "
                "'students.StudentExercise' model not found."
            )