# apps/users/management/commands/backfill_completed_enrollments.py
#
# One-time backfill: finds enrollments that are stuck at status='approved'
# but already have 100% progress (because the auto-complete signal didn't
# exist yet when they finished), and marks them as completed.
#
# Usage:
#   python manage.py backfill_completed_enrollments
#   python manage.py backfill_completed_enrollments --dry-run
#
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import Enrollment


class Command(BaseCommand):
    help = "Mark approved enrollments with 100% progress as completed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        approved = Enrollment.objects.filter(
            status=Enrollment.APPROVED
        ).select_related('student', 'course')

        total_checked = 0
        completed_count = 0

        for enrollment in approved:
            total_checked += 1
            progress = enrollment.progress  # triggers lazy computation

            if progress >= 100:
                completed_count += 1
                label = f"{enrollment.student.email} → {enrollment.course.title}"

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f"[DRY RUN] Would complete: {label}")
                    )
                else:
                    enrollment.status = Enrollment.COMPLETED
                    enrollment.completed_at = timezone.now()
                    enrollment.save(update_fields=['status', 'completed_at'])
                    self.stdout.write(
                        self.style.SUCCESS(f"Completed: {label}")
                    )

        self.stdout.write('')
        self.stdout.write(
            f"Checked {total_checked} approved enrollment(s), "
            f"{'would mark' if dry_run else 'marked'} {completed_count} as completed."
        )
        if dry_run:
            self.stdout.write(
                self.style.NOTICE("Run without --dry-run to apply these changes.")
            )