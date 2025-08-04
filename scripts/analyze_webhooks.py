#!/usr/bin/env python3
"""
Webhook Analysis Tool - Analyze captured webhook payloads

This script processes captured webhook JSON files to identify patterns,
cascades, and timing issues that cause the flashing CalSync busy blocks.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_webhook_data(logs_dir="logs/webhooks"):
    """Load all webhook JSON files from the logs directory"""
    webhook_data = []
    logs_path = Path(logs_dir)
    
    if not logs_path.exists():
        print(f"❌ Logs directory {logs_dir} not found")
        return []
    
    # Process all JSON files in all date directories
    for date_dir in logs_path.iterdir():
        if date_dir.is_dir():
            for json_file in date_dir.glob("webhook_*.json"):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        data['_file_path'] = str(json_file)
                        webhook_data.append(data)
                except Exception as e:
                    print(f"⚠️  Failed to load {json_file}: {e}")
    
    # Sort by timestamp
    webhook_data.sort(key=lambda x: x.get('timestamp', ''))
    return webhook_data


def analyze_webhook_patterns(webhook_data):
    """Analyze webhook patterns and identify potential cascades"""
    print("🔍 WEBHOOK PATTERN ANALYSIS")
    print("=" * 50)
    
    if not webhook_data:
        print("❌ No webhook data found")
        return
    
    # Basic statistics
    total_webhooks = len(webhook_data)
    calendars = set()
    message_numbers = []
    processing_decisions = defaultdict(int)
    calsync_events_found = 0
    
    print(f"📊 Total webhooks captured: {total_webhooks}")
    
    # Analyze each webhook
    for webhook in webhook_data:
        # Calendar tracking
        resource_id = webhook.get('resource_id')
        if resource_id:
            calendars.add(resource_id)
        
        # Message number tracking
        msg_num = webhook.get('message_number', 0)
        if msg_num > 0:
            message_numbers.append(msg_num)
        
        # Processing decisions
        decisions = webhook.get('processing_decisions', {})
        for decision_type in decisions.keys():
            processing_decisions[decision_type] += 1
        
        # Check for CalSync events in API response
        api_response = webhook.get('google_api_response', {})
        if api_response:
            events = api_response.get('events', [])
            for event in events:
                if event.get('is_calsync_busy_block', False):
                    calsync_events_found += 1
    
    print(f"📅 Unique calendars involved: {len(calendars)}")
    print(f"📈 Message number range: {min(message_numbers) if message_numbers else 'N/A'} - {max(message_numbers) if message_numbers else 'N/A'}")
    print(f"🔒 CalSync busy blocks found: {calsync_events_found}")
    
    # Processing decisions summary
    print(f"\n🎯 Processing Decisions:")
    for decision, count in processing_decisions.items():
        print(f"   {decision}: {count}")
    
    # Google API Response Analysis
    print(f"\n📊 GOOGLE API RESPONSE ANALYSIS:")
    analyze_google_api_responses(webhook_data)
    
    # Detect potential cascades
    print(f"\n🔄 CASCADE DETECTION:")
    detect_cascades(webhook_data)
    
    # Timing analysis
    print(f"\n⏰ TIMING ANALYSIS:")
    analyze_timing(webhook_data)


def analyze_google_api_responses(webhook_data):
    """Analyze Google API responses captured from webhooks"""
    api_responses = []
    total_events = 0
    calsync_events = 0
    
    for webhook in webhook_data:
        api_response = webhook.get('google_api_response')
        if api_response:
            api_responses.append(api_response)
            events = api_response.get('events', [])
            total_events += len(events)
            
            for event in events:
                if event.get('is_calsync_busy_block', False):
                    calsync_events += 1
                    print(f"   🔒 CalSync Busy Block: '{event.get('summary', 'No title')}' (ID: {event.get('id', 'unknown')})")
    
    if api_responses:
        print(f"   📊 API Responses: {len(api_responses)} webhooks made API calls")
        print(f"   📅 Total events returned: {total_events}")
        print(f"   🔒 CalSync busy blocks: {calsync_events}")
        
        if calsync_events > 0:
            print(f"   🚨 WARNING: {calsync_events} CalSync busy blocks detected - potential cascade source!")
    else:
        print("   ❌ No Google API response data found")


def detect_cascades(webhook_data):
    """Detect potential webhook cascades"""
    # Group webhooks by calendar
    calendar_webhooks = defaultdict(list)
    
    for webhook in webhook_data:
        resource_id = webhook.get('resource_id')
        if resource_id:
            calendar_webhooks[resource_id].append(webhook)
    
    # Look for rapid webhook sequences
    for calendar_id, webhooks in calendar_webhooks.items():
        if len(webhooks) > 5:  # More than 5 webhooks for one calendar
            print(f"   🚨 Calendar {calendar_id}: {len(webhooks)} webhooks (potential cascade)")
            
            # Check message number jumps
            msg_nums = [w.get('message_number', 0) for w in webhooks if w.get('message_number', 0) > 0]
            if len(msg_nums) > 1:
                jumps = [msg_nums[i+1] - msg_nums[i] for i in range(len(msg_nums)-1)]
                avg_jump = sum(jumps) / len(jumps) if jumps else 0
                print(f"      Average message number jump: {avg_jump:.1f}")
                
                # Large jumps indicate webhook storms
                large_jumps = [j for j in jumps if j > 1000]
                if large_jumps:
                    print(f"      🌪️  Webhook storm detected: {len(large_jumps)} large jumps")


def analyze_timing(webhook_data):
    """Analyze timing patterns in webhook arrivals"""
    if len(webhook_data) < 2:
        return
    
    timestamps = []
    for webhook in webhook_data:
        try:
            ts_str = webhook.get('timestamp', '')
            if ts_str:
                # Handle various timestamp formats
                if 'T' in ts_str:
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    ts = datetime.fromisoformat(ts_str)
                timestamps.append(ts)
        except Exception as e:
            continue
    
    if len(timestamps) < 2:
        print("   ❌ Insufficient timestamp data")
        return
    
    # Calculate intervals
    intervals = []
    for i in range(1, len(timestamps)):
        interval = (timestamps[i] - timestamps[i-1]).total_seconds()
        intervals.append(interval)
    
    # Timing statistics
    avg_interval = sum(intervals) / len(intervals)
    min_interval = min(intervals)
    max_interval = max(intervals)
    
    print(f"   📊 Webhook intervals (seconds):")
    print(f"      Average: {avg_interval:.2f}")
    print(f"      Minimum: {min_interval:.2f}")
    print(f"      Maximum: {max_interval:.2f}")
    
    # Detect rapid-fire webhooks (< 1 second apart)
    rapid_webhooks = [i for i in intervals if i < 1.0]
    if rapid_webhooks:
        print(f"      🚨 Rapid webhooks: {len(rapid_webhooks)} intervals < 1 second")


def generate_test_fixtures(webhook_data, output_dir="logs/webhooks/analysis/test_fixtures"):
    """Generate test fixtures from real webhook data"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n🧪 GENERATING TEST FIXTURES")
    print("=" * 50)
    
    # Group by interesting patterns
    fixtures = {
        'webhook_storm': [],
        'cascade_sequence': [],
        'normal_webhook': [],
        'throttled_webhook': [],
        'rate_limited_webhook': []
    }
    
    for webhook in webhook_data:
        decisions = webhook.get('processing_decisions', {})
        
        # Categorize webhooks
        if 'throttled' in decisions:
            fixtures['throttled_webhook'].append(webhook)
        elif 'rate_limited' in decisions:
            fixtures['rate_limited_webhook'].append(webhook)
        elif webhook.get('message_number', 0) > 10000:  # High message numbers indicate storms
            fixtures['webhook_storm'].append(webhook)
        else:
            fixtures['normal_webhook'].append(webhook)
    
    # Save fixtures
    for fixture_type, data in fixtures.items():
        if data:
            fixture_file = output_path / f"{fixture_type}_fixtures.json"
            with open(fixture_file, 'w') as f:
                json.dump(data[:5], f, indent=2, default=str)  # Limit to 5 examples
            print(f"   💾 Saved {len(data[:5])} {fixture_type} fixtures to {fixture_file}")


def main():
    """Main analysis function"""
    print("🔧 WEBHOOK ANALYSIS TOOL")
    print("=" * 50)
    
    # Load webhook data
    webhook_data = load_webhook_data()
    
    if not webhook_data:
        print("❌ No webhook data found. Make sure to capture some webhooks first!")
        sys.exit(1)
    
    # Run analysis
    analyze_webhook_patterns(webhook_data)
    
    # Generate test fixtures
    generate_test_fixtures(webhook_data)
    
    print(f"\n✅ Analysis complete!")
    print(f"📁 Check logs/webhooks/analysis/ for detailed results")


if __name__ == "__main__":
    main()