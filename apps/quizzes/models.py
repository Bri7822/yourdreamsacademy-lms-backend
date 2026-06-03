"""
apps/quizzes/models.py

StudentExercise tracks per-student exercise completion for a lesson.
Previously lived in student_dashboard.models.
"""

from django.db import models
from django.utils import timezone


class StudentExercise(models.Model):
    student = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='student_exercises',
    )
    lesson = models.ForeignKey(
        'lessons.Lesson',
        on_delete=models.CASCADE,
        related_name='student_exercises',
    )
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0.0)

    # Student's submitted answer(s)
    submission = models.JSONField(blank=True, null=True)

    class Meta:
        app_label = 'quizzes'
        unique_together = ('student', 'lesson')
        ordering = ['lesson__order']

    def __str__(self):
        return f"{self.student.email} | {self.lesson.title} | completed={self.completed}"

    def mark_complete(self, score: float = 0.0):
        self.completed = True
        self.completed_at = timezone.now()
        self.score = score
        self.save()