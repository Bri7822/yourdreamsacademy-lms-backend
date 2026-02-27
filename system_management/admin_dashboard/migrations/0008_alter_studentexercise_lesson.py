from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('admin_dashboard', '0007_alter_studentexercise_lesson'),  # Replace with your last migration
    ]

    operations = [
        migrations.AddField(
            model_name='studentexercise',
            name='lesson',
            field=models.ForeignKey(
                default=1,  # You'll need to handle this default value
                on_delete=django.db.models.deletion.CASCADE,
                to='admin_dashboard.lesson'
            ),
            preserve_default=False,
        ),
    ]