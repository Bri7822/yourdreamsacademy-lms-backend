from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ("admin_dashboard", "0017_delete_studentexercise"),
        ("student_dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE student_dashboard_studentexercise SET score = 0.0 WHERE score IS NULL;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]