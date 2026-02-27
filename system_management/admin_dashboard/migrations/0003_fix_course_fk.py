# admin_dashboard/migrations/0003_fix_course_fk.py
from django.db import migrations


def forwards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            # Drop any constraints that reference the stale admin_dashboard_course table
            cursor.execute(
                """
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT conname, t.relname AS table_name
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    JOIN pg_class rcl ON c.confrelid = rcl.oid
    WHERE rcl.relname = 'admin_dashboard_course'
  LOOP
    EXECUTE 'ALTER TABLE ' || quote_ident(r.table_name) || ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.conname);
  END LOOP;
END$$;
                """
            )

            # Drop the stale admin_dashboard_course table if it exists
            cursor.execute("DROP TABLE IF EXISTS admin_dashboard_course CASCADE;")

            # Check if accounts_course table exists
            cursor.execute(
                """
SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name = 'accounts_course'
);
                """
            )
            accounts_course_exists = cursor.fetchone()[0]

            if accounts_course_exists:
                # Re-create correct foreign keys pointing to accounts_course if they don't already exist
                cursor.execute(
                    """
DO $$
BEGIN
  -- admin_dashboard_enrollment
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'admin_dashboard_enrollment') THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'admin_dashboard_enrollment_course_id_accounts_fk'
      AND table_name = 'admin_dashboard_enrollment'
    ) THEN
      -- Drop existing FK constraints if any
      IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY'
        AND table_name = 'admin_dashboard_enrollment'
        AND constraint_name LIKE '%course_id%'
      ) THEN
        ALTER TABLE admin_dashboard_enrollment DROP CONSTRAINT IF EXISTS admin_dashboard_enrollment_course_id_fkey;
        ALTER TABLE admin_dashboard_enrollment DROP CONSTRAINT IF EXISTS admin_dashboard_enrollment_course_id_fk;
      END IF;

      ALTER TABLE admin_dashboard_enrollment
        ADD CONSTRAINT admin_dashboard_enrollment_course_id_accounts_fk
        FOREIGN KEY (course_id) REFERENCES accounts_course(id) DEFERRABLE INITIALLY DEFERRED;
    END IF;
  END IF;

  -- admin_dashboard_lesson
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'admin_dashboard_lesson') THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.table_constraints
      WHERE constraint_name = 'admin_dashboard_lesson_course_id_accounts_fk'
      AND table_name = 'admin_dashboard_lesson'
    ) THEN
      -- Drop existing FK constraints if any
      IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY'
        AND table_name = 'admin_dashboard_lesson'
        AND constraint_name LIKE '%course_id%'
      ) THEN
        ALTER TABLE admin_dashboard_lesson DROP CONSTRAINT IF EXISTS admin_dashboard_lesson_course_id_fkey;
        ALTER TABLE admin_dashboard_lesson DROP CONSTRAINT IF EXISTS admin_dashboard_lesson_course_id_fk;
      END IF;

      ALTER TABLE admin_dashboard_lesson
        ADD CONSTRAINT admin_dashboard_lesson_course_id_accounts_fk
        FOREIGN KEY (course_id) REFERENCES accounts_course(id) DEFERRABLE INITIALLY DEFERRED;
    END IF;
  END IF;

  -- Notice if accounts_course somehow doesn't exist (optional)
  -- RAISE NOTICE 'accounts_course table exists and FK constraints created.';
END$$;
                    """
                )
            else:
                # Optional: just  in Python, not SQL
                ("accounts_course table does not exist. Skipping foreign key creation.")
        else:
            # For sqlite/mysql or other vendors, skip as this fix targets Postgres specifically
            pass


def backwards(apps, schema_editor):
    # No-op reverse; we don't want to re-create the stale table or constraints
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_dashboard', '0002_enrollment_notes'),
        ('accounts', '0001_initial'),  # Make sure accounts app is migrated first
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
