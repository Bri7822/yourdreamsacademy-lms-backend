# admin_dashboard/migrations/0018_fix_null_scores.py
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        # This will be automatically set to the correct previous migration
        ('admin_dashboard', '0017_delete_studentexercise'),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE student_dashboard_studentexercise SET score = 0.0 WHERE score IS NULL;",
            reverse_sql=migrations.RunSQL.noop
        ),
        # If you want to enforce NOT NULL at database level:
        migrations.RunSQL(
            "ALTER TABLE student_dashboard_studentexercise ALTER COLUMN score SET NOT NULL;",
            reverse_sql="ALTER TABLE student_dashboard_studentexercise ALTER COLUMN score DROP NOT NULL;"
        ),
    ]