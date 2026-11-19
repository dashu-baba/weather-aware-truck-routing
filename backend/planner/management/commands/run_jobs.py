import time

from django.core.management.base import BaseCommand

from planner.jobs import JobRunner, recover_stale_jobs, run_pending
from routing.openmeteo import OpenMeteoProvider


class Command(BaseCommand):
    help = "Run the weather job worker: fetch forecasts for queued plan jobs, one job at a time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Process the queue until it is empty, then exit."
        )

    def handle(self, *args, **options):
        provider = OpenMeteoProvider()
        if options["once"]:
            recover_stale_jobs()
            self.stdout.write(f"Processed {run_pending(provider)} job(s).")
            return
        runner = JobRunner(provider)
        runner.start()
        self.stdout.write("Weather job worker running. Press Ctrl+C to stop.")
        try:
            while runner.alive:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            runner.stop()
