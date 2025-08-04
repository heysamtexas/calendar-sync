"""Django management command for running calendar sync scheduler"""

import signal
import sys
import threading
import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Run long-running scheduler for calendar sync and token refresh tasks"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self.threads = []
        
    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-interval",
            type=int,
            default=15,
            help="Calendar sync interval in minutes (default: 15)",
        )
        parser.add_argument(
            "--token-interval", 
            type=int,
            default=60,
            help="Token refresh interval in minutes (default: 60)",
        )
        parser.add_argument(
            "--validation-interval",
            type=int, 
            default=1440,  # 24 hours
            help="Full token validation interval in minutes (default: 1440 = 24 hours)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true", 
            help="Show what would run without executing tasks",
        )

    def handle(self, *args, **options):
        self.verbose = options["verbose"]
        self.dry_run = options["dry_run"]
        
        # Convert minutes to seconds
        sync_interval = options["sync_interval"] * 60
        token_interval = options["token_interval"] * 60  
        validation_interval = options["validation_interval"] * 60
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Calendar Sync Scheduler\n"
                f"  Sync interval: {options['sync_interval']} minutes\n"
                f"  Token refresh interval: {options['token_interval']} minutes\n" 
                f"  Token validation interval: {options['validation_interval']} minutes\n"
                f"  Verbose: {self.verbose}\n"
                f"  Dry run: {self.dry_run}"
            )
        )
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No tasks will be executed"))
            return
            
        try:
            # Start scheduler threads
            self._start_scheduler_threads(sync_interval, token_interval, validation_interval)
            
            # Main loop - keep the process alive
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self._shutdown()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Scheduler error: {e}"))
            self._shutdown()
            
    def _start_scheduler_threads(self, sync_interval, token_interval, validation_interval):
        """Start all scheduler threads"""
        
        # Calendar sync thread
        sync_thread = threading.Thread(
            target=self._run_periodic_task,
            args=("sync_calendars", sync_interval, "Calendar Sync"),
            daemon=True
        )
        sync_thread.start()
        self.threads.append(sync_thread)
        
        # Token refresh thread  
        token_thread = threading.Thread(
            target=self._run_periodic_task,
            args=("refresh_tokens", token_interval, "Token Refresh", ["--background"]),
            daemon=True
        )
        token_thread.start()
        self.threads.append(token_thread)
        
        # Token validation thread
        validation_thread = threading.Thread(
            target=self._run_periodic_task, 
            args=("refresh_tokens", validation_interval, "Token Validation", []),
            daemon=True
        )
        validation_thread.start()
        self.threads.append(validation_thread)
        
        self.stdout.write(f"Started {len(self.threads)} scheduler threads")
        
    def _run_periodic_task(self, command, interval, task_name, extra_args=None):
        """Run a Django management command periodically"""
        extra_args = extra_args or []
        last_run = 0
        
        while self.running:
            current_time = time.time()
            
            # Check if it's time to run the task
            if current_time - last_run >= interval:
                try:
                    if self.verbose:
                        self.stdout.write(f"[{datetime.now()}] Running {task_name}...")
                        
                    # Run the Django management command
                    call_command(command, *extra_args, verbosity=0)
                    
                    if self.verbose:
                        self.stdout.write(
                            self.style.SUCCESS(f"[{datetime.now()}] {task_name} completed")
                        )
                        
                    last_run = current_time
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"[{datetime.now()}] {task_name} failed: {e}")
                    )
                    # Continue running even if one task fails
                    last_run = current_time
                    
            # Sleep for 10 seconds before checking again
            time.sleep(10)
            
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.stdout.write(f"\nReceived signal {signum}, shutting down gracefully...")
        self._shutdown()
        
    def _shutdown(self):
        """Graceful shutdown"""
        self.running = False
        
        self.stdout.write("Waiting for running tasks to complete...")
        
        # Give threads time to finish current tasks
        time.sleep(5)
        
        self.stdout.write(self.style.SUCCESS("Scheduler stopped"))
        sys.exit(0)