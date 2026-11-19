from django.core.management.base import BaseCommand

from planner.storage import cleanup_expired


class Command(BaseCommand):
    help = "Delete expired plans, weather jobs and their data files."

    def handle(self, *args, **options):
        counts = cleanup_expired()
        self.stdout.write(
            f"Removed {counts['plans']} plan(s), {counts['jobs']} weather job(s), {counts['files']} file(s)."
        )
