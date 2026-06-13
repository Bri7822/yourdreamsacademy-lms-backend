"""
Run with:  python manage.py shell < dump_debug.py
(or paste into `python manage.py shell` interactively)

Dumps:
  1. Raw `exercise` JSON for lesson id=2 (the one from your last test session)
  2. For each active course, the exercise_count the LessonListSerializer
     would compute per lesson, plus the raw `exercise` field's Python type.
"""
import json
from apps.students.compat import Lesson, Course

print("\n" + "=" * 70)
print("LESSON 2 RAW EXERCISE FIELD")
print("=" * 70)
lesson2 = Lesson.objects.filter(id=2).first()
if lesson2:
    print("type:", type(lesson2.exercise))
    print(json.dumps(lesson2.exercise, indent=2, default=str))
else:
    print("Lesson id=2 not found")

print("\n" + "=" * 70)
print("ALL ACTIVE COURSES / LESSONS / EXERCISE FIELD TYPES")
print("=" * 70)
for course in Course.objects.filter(is_active=True).order_by('code'):
    print(f"\n--- Course {course.code} (id={course.id}) ---")
    lessons = Lesson.objects.filter(course=course, is_active=True).order_by('order')
    for lesson in lessons:
        ex = lesson.exercise
        ex_type = type(ex).__name__
        if isinstance(ex, dict):
            keys = list(ex.keys())
        elif isinstance(ex, list):
            keys = f"list len={len(ex)}"
        elif isinstance(ex, str):
            keys = f"string len={len(ex)}: {ex[:60]!r}"
        else:
            keys = repr(ex)
        print(f"  Lesson {lesson.id} '{lesson.title}': exercise type={ex_type}, content={keys}")