from django.core.management.base import BaseCommand
from student_dashboard.models import StudentExercise
from admin_dashboard.models import Lesson

class Command(BaseCommand):
    help = 'Recalculate and fix scores for all completed exercises'

    def handle(self, *args, **options):
        self.stdout.write("🔧 Fixing scores for completed exercises...")

        exercises = StudentExercise.objects.filter(completed=True)
        fixed_count = 0

        for exercise in exercises:
            if not exercise.submission_data:
                self.stdout.write(f"  ⚠️ {exercise.lesson.title}: No submission data")
                continue

            # Count correct answers from submission_data
            correct_count = 0
            for question_id, submission in exercise.submission_data.items():
                if isinstance(submission, dict) and submission.get('is_correct'):
                    correct_count += 1

            if correct_count > 0:
                exercise.score = float(correct_count)
                exercise.save()
                fixed_count += 1
                self.stdout.write(
                    f"  ✅ {exercise.lesson.title}: Set score to {correct_count}"
                )
            else:
                self.stdout.write(
                    f"  ⚠️ {exercise.lesson.title}: No correct answers found"
                )

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Fixed {fixed_count} exercises!")
        )