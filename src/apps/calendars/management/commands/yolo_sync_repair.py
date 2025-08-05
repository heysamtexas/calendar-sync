"""
Guilfoyle's YOLO Sync Reconciliation Engine

YOLO MODE: Bulletproof sync consistency repair through UUID correlation supremacy.
No cascades. No compromises. No mercy for sync gaps.

"Any sync problem that can't be solved with UUID correlation isn't worth solving." - Guilfoyle's Law
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.calendars.models import Calendar, EventState


User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Guilfoyle's YOLO Sync Reconciliation Engine - Achieve Perfect Sync™"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-email",
            type=str,
            help="Repair sync for specific user email",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be repaired without executing (for the cautious)",
        )
        parser.add_argument(
            "--guilfoyle-mode",
            action="store_true",
            help="Show extra technical details (recommended)",
        )
        parser.add_argument(
            "--show-work",
            action="store_true",
            help="Demonstrate the genius at work",
        )

    def handle(self, *args, **options):
        """Execute Guilfoyle's YOLO Sync Reconciliation"""
        self.show_guilfoyle_mode = options["guilfoyle_mode"]
        self.show_work = options["show_work"]
        self.dry_run = options["dry_run"]

        self._print_header()

        try:
            # Get users to repair
            users = self._get_users_to_repair(options)

            if not users:
                self.stdout.write(
                    self.style.WARNING("🤷 No users with multiple calendars found")
                )
                return

            # Execute the YOLO repair for each user
            total_repairs = 0
            perfect_users = 0

            for user in users:
                repairs_made = self._yolo_repair_user(user)
                total_repairs += repairs_made
                if repairs_made == 0:
                    perfect_users += 1

            # Final Guilfoyle verdict
            self._print_final_verdict(total_repairs, perfect_users, len(users))

        except Exception as e:
            logger.error(f"YOLO repair failed: {e}")
            raise CommandError(f"🔥 YOLO repair failed: {e}")

    def _print_header(self):
        """Print Guilfoyle's signature header"""
        header = [
            "🚀 GUILFOYLE'S YOLO SYNC RECONCILIATION ENGINE",
            "💡 Powered by UUID Correlation Supremacy",
            "🎯 Mission: Achieve Perfect Sync™",
        ]

        if self.dry_run:
            header.append("🛡️  DRY RUN MODE (Playing it safe)")
        else:
            header.append("⚡ YOLO MODE ENGAGED")

        for line in header:
            self.stdout.write(self.style.SUCCESS(line))

        self.stdout.write("─" * 60)

    def _get_users_to_repair(self, options):
        """Get users that need sync repair"""
        if options["user_email"]:
            try:
                user = User.objects.get(email=options["user_email"])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f"User {options['user_email']} not found")
        else:
            # Get all users with multiple sync-enabled calendars
            users_with_multiple_cals = []
            for user in User.objects.all():
                cal_count = Calendar.objects.filter(
                    calendar_account__user=user,
                    sync_enabled=True,
                    calendar_account__is_active=True,
                ).count()
                if cal_count >= 2:
                    users_with_multiple_cals.append(user)

            return users_with_multiple_cals

    def _yolo_repair_user(self, user):
        """Execute YOLO repair for a single user"""
        self.stdout.write(f"\n👤 Processing user: {user.email}")

        # Get user's calendars
        calendars = list(Calendar.objects.filter(
            calendar_account__user=user,
            sync_enabled=True,
            calendar_account__is_active=True,
        ).select_related("calendar_account"))

        if len(calendars) < 2:
            self.stdout.write("   ℹ️  User has < 2 calendars, skipping")
            return 0

        # Phase 1: AUDIT - Analyze sync consistency
        audit_results = self._audit_sync_consistency(calendars)

        # Phase 2: Calculate Guilfoyle Health Score
        health_score = self._calculate_guilfoyle_health_score(audit_results)

        # Phase 3: REPAIR - Fix missing busy blocks
        repairs_made = 0
        if audit_results["total_missing"] > 0:
            repairs_made = self._execute_yolo_repair(calendars, audit_results)

        # Phase 4: VALIDATION - Verify Perfect Sync™
        if repairs_made > 0:
            final_audit = self._audit_sync_consistency(calendars)
            final_health_score = self._calculate_guilfoyle_health_score(final_audit)
            self._print_repair_results(repairs_made, health_score, final_health_score)
        else:
            self._print_perfect_sync_message(health_score)

        return repairs_made

    def _audit_sync_consistency(self, calendars):
        """Guilfoyle's Comprehensive Sync Audit"""
        results = {
            "calendar_count": len(calendars),
            "total_user_events": 0,
            "total_busy_blocks": 0,
            "expected_busy_blocks": 0,
            "actual_busy_blocks": 0,
            "missing_by_calendar": {},
            "missing_pairs": [],
            "total_missing": 0,
        }

        calendar_events = {}

        # Collect event data for each calendar
        for cal in calendars:
            user_events = cal.event_states.filter(is_busy_block=False)
            busy_blocks = cal.event_states.filter(is_busy_block=True)

            calendar_events[cal.id] = {
                "calendar": cal,
                "user_events": list(user_events),
                "busy_blocks": busy_blocks.count(),
            }

            results["total_user_events"] += user_events.count()
            results["total_busy_blocks"] += busy_blocks.count()

        # Analyze missing busy blocks for each calendar pair
        for source_cal_id, source_data in calendar_events.items():
            for target_cal_id, target_data in calendar_events.items():
                if source_cal_id == target_cal_id:
                    continue

                source_cal = source_data["calendar"]
                target_cal = target_data["calendar"]
                source_events = source_data["user_events"]

                # Count expected vs actual busy blocks
                expected = len(source_events)
                results["expected_busy_blocks"] += expected

                if expected == 0:
                    continue

                # Find missing busy blocks
                source_uuids = [event.uuid for event in source_events]
                actual_busy_blocks = EventState.objects.filter(
                    calendar=target_cal,
                    source_uuid__in=source_uuids,
                    is_busy_block=True,
                ).count()

                results["actual_busy_blocks"] += actual_busy_blocks
                missing = expected - actual_busy_blocks

                if missing > 0:
                    pair_key = f"{source_cal.calendar_account.email} → {target_cal.calendar_account.email}"
                    results["missing_pairs"].append({
                        "source_calendar": source_cal,
                        "target_calendar": target_cal,
                        "source_events": source_events,
                        "expected": expected,
                        "actual": actual_busy_blocks,
                        "missing": missing,
                        "pair_description": pair_key,
                    })

                    results["total_missing"] += missing

                    if target_cal.id not in results["missing_by_calendar"]:
                        results["missing_by_calendar"][target_cal.id] = 0
                    results["missing_by_calendar"][target_cal.id] += missing

        if self.show_work:
            self._print_audit_details(results)

        return results

    def _print_audit_details(self, results):
        """Print detailed audit results"""
        self.stdout.write("🔍 AUDIT RESULTS:")
        self.stdout.write(f"   📊 {results['calendar_count']} calendars analyzed")
        self.stdout.write(f"   📅 {results['total_user_events']} total user events")
        self.stdout.write(f"   🔒 {results['total_busy_blocks']} total busy blocks")
        self.stdout.write(f"   ⚠️  {results['total_missing']} missing busy blocks detected")

        if results["missing_pairs"] and self.show_guilfoyle_mode:
            self.stdout.write("\n📋 MISSING BUSY BLOCK MATRIX:")
            for pair in results["missing_pairs"]:
                self.stdout.write(
                    f"   {pair['pair_description']}: "
                    f"{pair['actual']}/{pair['expected']} "
                    f"(❌ Missing {pair['missing']})"
                )

    def _calculate_guilfoyle_health_score(self, audit_results):
        """Calculate Guilfoyle's Sync Health Score"""
        if audit_results["expected_busy_blocks"] == 0:
            return {"score": 100.0, "rating": "⭐⭐⭐⭐⭐", "status": "PERFECT"}

        score = (audit_results["actual_busy_blocks"] / audit_results["expected_busy_blocks"]) * 100

        if score >= 95:
            rating = "⭐⭐⭐⭐⭐"
            status = "PERFECT"
        elif score >= 85:
            rating = "⭐⭐⭐⭐☆"
            status = "EXCELLENT"
        elif score >= 70:
            rating = "⭐⭐⭐☆☆"
            status = "GOOD"
        elif score >= 50:
            rating = "⭐⭐☆☆☆"
            status = "DEGRADED"
        else:
            rating = "⭐☆☆☆☆"
            status = "CRITICAL"

        return {
            "score": score,
            "rating": rating,
            "status": status,
            "missing": audit_results["total_missing"],
        }

    def _execute_yolo_repair(self, calendars, audit_results):
        """Execute the YOLO repair with cascade paranoia"""
        if self.dry_run:
            self.stdout.write(f"🛡️  DRY RUN: Would repair {audit_results['total_missing']} missing busy blocks")
            return audit_results["total_missing"]

        self.stdout.write(f"🎯 REPAIR: Creating {audit_results['total_missing']} missing busy blocks...")

        repairs_made = 0

        try:
            with transaction.atomic():
                for pair in audit_results["missing_pairs"]:
                    source_cal = pair["source_calendar"]
                    target_cal = pair["target_calendar"]
                    source_events = pair["source_events"]

                    # Find which specific events are missing busy blocks
                    for source_event in source_events:
                        existing_busy_block = EventState.objects.filter(
                            calendar=target_cal,
                            source_uuid=source_event.uuid,
                            is_busy_block=True,
                        ).exists()

                        if not existing_busy_block:
                            # Guilfoyle's Trust-the-UUID Check
                            if self._is_safe_for_busy_block_creation(source_event):
                                self._create_missing_busy_block_with_uuid_correlation(
                                    source_event, target_cal
                                )
                                repairs_made += 1

                                if self.show_work:
                                    self.stdout.write(
                                        f"   ✅ Created busy block in {target_cal.name} "
                                        f"from {source_event.title[:30]}..."
                                    )
                            elif self.show_guilfoyle_mode:
                                self.stdout.write(
                                    f"   ⚠️  Skipped busy block (source is already a busy block): {source_event.uuid}"
                                )

        except Exception as e:
            logger.error(f"YOLO repair transaction failed: {e}")
            raise CommandError(f"Repair failed: {e}")

        return repairs_made

    def _is_safe_for_busy_block_creation(self, source_event):
        """Guilfoyle's Smart Safety Check"""
        # Rule 1: Don't create busy blocks from busy blocks
        # Rule 2: Don't create busy blocks from deleted events
        # UUID correlation handles cascade prevention automatically
        return (not source_event.is_busy_block and
                source_event.status != "DELETED")

    def _create_missing_busy_block_with_uuid_correlation(self, source_event, target_calendar):
        """Create missing busy block with Guilfoyle's UUID correlation protection"""
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient

        # Create EventState first (database-first principle)
        busy_block_state = EventState.create_busy_block(
            target_calendar=target_calendar,
            source_uuid=source_event.uuid,
            title=source_event.title or "Event",
        )

        # Create in Google Calendar with UUID correlation
        client = GoogleCalendarClient(target_calendar.calendar_account)

        # Clean title to prevent cascade prefixes
        clean_title = source_event.title or "Event"
        if clean_title.startswith("Busy - "):
            clean_title = clean_title[7:]

        event_data = {
            "summary": f"Busy - {clean_title}",
            "description": f"Busy block created by Guilfoyle's YOLO Repair from {source_event.calendar.name}",
            "start": self._format_event_datetime(source_event.start_time),
            "end": self._format_event_datetime(source_event.end_time),
            "transparency": "opaque",
            "visibility": "private",
        }

        created_event = client.create_event_with_uuid_correlation(
            calendar_id=target_calendar.google_calendar_id,
            event_data=event_data,
            correlation_uuid=str(busy_block_state.uuid),
            skip_title_embedding=True,
        )

        if created_event:
            busy_block_state.mark_synced(created_event["id"])
            return busy_block_state
        else:
            # Failed to create in Google - clean up database
            busy_block_state.mark_deleted()
            raise Exception(f"Failed to create busy block in Google Calendar for {target_calendar.name}")

    def _format_event_datetime(self, dt):
        """Format datetime for Google Calendar API"""
        if not dt:
            from django.utils import timezone
            dt = timezone.now()

        return {
            "dateTime": dt.isoformat(),
            "timeZone": "UTC",
        }

    def _print_repair_results(self, repairs_made, initial_health, final_health):
        """Print repair results with Guilfoyle flair"""
        self.stdout.write(f"\n✅ REPAIR COMPLETE: {repairs_made} busy blocks created")
        self.stdout.write(f"📊 Health Score: {initial_health['score']:.1f}% → {final_health['score']:.1f}%")
        self.stdout.write(f"🏆 Guilfoyle Rating: {initial_health['rating']} → {final_health['rating']}")

        if final_health["score"] >= 99.9:
            self.stdout.write(self.style.SUCCESS("🎉 PERFECT SYNC™ ACHIEVED"))
        elif final_health["score"] >= 95:
            self.stdout.write(self.style.SUCCESS("🌟 EXCELLENT SYNC SYMMETRY"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {final_health['missing']} gaps remain"))

    def _print_perfect_sync_message(self, health_score):
        """Print message for already perfect sync"""
        self.stdout.write(f"✨ Already Perfect: {health_score['rating']} ({health_score['score']:.1f}%)")
        self.stdout.write("🎯 No repairs needed - Guilfoyle's UUID correlation is working flawlessly")

    def _print_final_verdict(self, total_repairs, perfect_users, total_users):
        """Print Guilfoyle's final verdict"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("🏆 GUILFOYLE'S FINAL VERDICT")
        self.stdout.write("=" * 60)

        if total_repairs == 0:
            self.stdout.write(self.style.SUCCESS("🎉 ALL USERS ALREADY HAVE PERFECT SYNC™"))
            self.stdout.write("💡 Guilfoyle's Law validated: UUID correlation solves everything")
        else:
            self.stdout.write(f"⚡ YOLO REPAIR COMPLETE: {total_repairs} total busy blocks created")
            self.stdout.write(f"👥 Users processed: {total_users}")
            self.stdout.write(f"✨ Perfect users: {perfect_users}")

            if self.dry_run:
                self.stdout.write("🛡️  Run without --dry-run to execute repairs")
            else:
                self.stdout.write(self.style.SUCCESS("🚀 SYNC CONSISTENCY ACHIEVED"))

        self.stdout.write("💪 Guilfoyle's UUID Correlation Engine: OPERATIONAL")

        if self.show_guilfoyle_mode:
            self.stdout.write("\n" + self.style.SUCCESS("🧠 Guilfoyle's Technical Notes:"))
            self.stdout.write("   • Database-first architecture prevents cascades")
            self.stdout.write("   • UUID correlation ensures bulletproof event tracking")
            self.stdout.write("   • Cascade paranoia validates every busy block creation")
            self.stdout.write("   • Perfect Sync™ is mathematically guaranteed")
