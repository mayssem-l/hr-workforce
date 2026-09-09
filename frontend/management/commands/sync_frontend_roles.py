from django.core.management.base import BaseCommand

from frontend.roles import ROLE_PERMISSION_MAP, sync_role_permissions


class Command(BaseCommand):
    help = "Create frontend role groups and synchronize their model permissions."

    def handle(self, *args, **options):
        sync_role_permissions()
        self.stdout.write(
            self.style.SUCCESS(
                f"Synchronized {len(ROLE_PERMISSION_MAP)} frontend roles."
            )
        )
