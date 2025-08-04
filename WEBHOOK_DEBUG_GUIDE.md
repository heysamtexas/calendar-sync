# Webhook Debugging Guide

This guide explains how to use the enhanced webhook payload capture system to debug the CalSync busy block flashing issue.

## 🎯 Quick Start

1. **Let webhooks come in naturally** - the system automatically captures all webhook payloads
2. **Check logs directory**: `src/logs/webhooks/YYYY-MM-DD/`  
3. **Run analysis**: `python scripts/analyze_webhooks.py` (from project root)
4. **Review results**: Check `src/logs/webhooks/analysis/` for patterns and fixtures

## 📁 File Structure

```
src/logs/webhooks/
├── 2025-08-04/                              # Daily webhook logs
│   ├── webhook_143022_calendar123_12345.json # Timestamped webhook payloads
│   └── webhook_143045_calendar456_12380.json
└── analysis/
    ├── cascade_patterns.json               # Detected cascade patterns  
    └── test_fixtures/
        ├── normal_webhook_fixtures.json   # Normal webhook examples
        ├── webhook_storm_fixtures.json    # Storm patterns
        └── throttled_webhook_fixtures.json # Throttled examples
```

## 🔍 Webhook Payload Structure

Each captured webhook contains:

```json
{
  "timestamp": "2025-08-04T14:30:22.123456",
  "channel_id": "calendar-sync-abc123",
  "resource_id": "samtexas@ibxadvisors.com",
  "message_number": 12345,
  "processing_decisions": {
    "throttled": {
      "reason": "Webhook storm detected",
      "timestamp": "2025-08-04T14:30:22.124000",
      "current_message_num": 12345,
      "last_message_num": 12342
    }
  },
  "calendar_context": {
    "calendar_name": "Sam's Calendar",
    "account_email": "samtexas@ibxadvisors.com",
    "sync_enabled": true,
    "last_synced": "2025-08-04T14:25:00.000000"
  },
  "sync_results": {
    "events_created": 0,
    "events_updated": 1,
    "events_deleted": 0,
    "errors": []
  }
}
```

## 🔧 Analysis Features

The analysis script (`scripts/analyze_webhooks.py`) provides:

### 📊 Pattern Detection
- **Webhook storms**: Rapid message number jumps (>1000)
- **Cascades**: Multiple webhooks for same calendar in short time
- **Timing patterns**: Average intervals, rapid-fire sequences
- **Processing decisions**: Throttled, rate limited, failed webhooks

### 🧪 Test Fixture Generation
Automatically creates test fixtures from real webhook patterns:
- `normal_webhook_fixtures.json` - Typical webhook behavior
- `webhook_storm_fixtures.json` - High-frequency webhook storms  
- `cascade_sequence_fixtures.json` - Webhook cascade patterns
- `throttled_webhook_fixtures.json` - Throttled webhook examples

## 🚨 Debugging the Flashing CalSync Issue

### Expected Pattern for Flashing Issue:
1. **Webhook arrives** for CalSync busy block creation
2. **Message numbers jump** rapidly (indicating webhook storm)
3. **Multiple calendars involved** in cascade
4. **Processing decisions** show throttling attempts
5. **Sync results** show busy blocks being created/deleted repeatedly

### Key Analysis Commands:
```bash
# Run from project root
python scripts/analyze_webhooks.py

# Look for these indicators:
# - "Webhook storm detected" in CASCADE DETECTION
# - Large message number jumps (>1000)
# - Multiple webhooks per calendar (>5)
# - Rapid webhook intervals (<1 second)
```

## 🎯 Next Steps

1. **Capture Real Webhook Data**: Let the system run during the flashing issue
2. **Analyze Patterns**: Use the analysis script to identify cascade triggers
3. **Build Targeted Tests**: Use generated fixtures to create specific test cases
4. **Implement Surgical Fixes**: Address the exact patterns causing issues

## 🔗 Integration with Existing Code

The webhook capture integrates seamlessly with existing functionality:
- **Stderr output**: Still provides immediate debugging info
- **Normal processing**: All webhook processing continues as before
- **No performance impact**: File I/O is minimal and non-blocking
- **Test compatibility**: Works with existing webhook tests

## 📈 Success Metrics

You'll know the debugging is working when:
- ✅ Webhook payload files are being created in `src/logs/webhooks/`
- ✅ Analysis script identifies cascade patterns
- ✅ Test fixtures are generated from real webhook data
- ✅ You can correlate flashing issues with specific webhook patterns

This system transforms webhook debugging from guesswork into data-driven analysis.