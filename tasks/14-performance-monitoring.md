# TASK-14: Performance Monitoring

## Priority: MEDIUM
## Estimated Time: 3-4 hours
## Dependencies: TASK-13 (Code Quality Improvements)

## Problem Statement

Guilfoyle identified the lack of performance monitoring and observability in the application, which creates blind spots for production operations and makes it difficult to identify and resolve performance issues:

### Performance Monitoring Gaps:
1. **No Application Performance Monitoring (APM)**
   - No metrics collection for response times
   - No database query performance tracking
   - No error rate monitoring
   - No user experience metrics

2. **Limited Observability**
   - Basic logging without structured format
   - No correlation IDs for request tracing
   - No performance alerts or dashboards
   - No capacity planning metrics

3. **Missing Production Insights**
   - No Google API rate limit monitoring
   - No sync operation performance tracking
   - No user behavior analytics
   - No resource utilization monitoring

4. **Development Performance Gaps**
   - No performance regression detection
   - No database query analysis in development
   - No load testing framework
   - No performance budgets

## Acceptance Criteria

- [ ] Application performance monitoring implemented
- [ ] Database query performance tracked and optimized
- [ ] Google API usage monitoring and alerting
- [ ] Structured logging with correlation IDs
- [ ] Performance metrics dashboard created
- [ ] Automated performance regression detection
- [ ] Load testing framework established
- [ ] Production monitoring and alerting configured
- [ ] Performance budgets defined and enforced
- [ ] Observability documentation completed

## Implementation Steps

### Step 1: APM and Metrics Infrastructure (1.5 hours)

1. **Django Performance Monitoring**
   - Integrate Django Debug Toolbar for development
   - Add response time middleware
   - Implement database query tracking
   - Create custom metrics collectors

2. **Structured Logging Setup**
   - Configure structured JSON logging
   - Add correlation ID middleware
   - Implement request/response logging
   - Add performance-specific log formats

3. **Metrics Collection Framework**
   - Choose metrics backend (Prometheus/StatsD)
   - Create custom metrics decorators
   - Add business logic metrics
   - Configure metrics endpoints

### Step 2: Database and API Performance Monitoring (1 hour)

1. **Database Query Optimization**
   - Add query performance logging
   - Implement slow query detection
   - Create N+1 query alerts
   - Add query plan analysis

2. **Google API Monitoring**
   - Track API request rates and quotas
   - Monitor response times and errors
   - Implement rate limit alerting
   - Add API usage analytics

3. **Cache Performance Monitoring**
   - Track cache hit/miss rates
   - Monitor cache performance
   - Add cache usage metrics
   - Implement cache warming strategies

### Step 3: User Experience and Business Metrics (1 hour)

1. **User Experience Monitoring**
   - Track page load times
   - Monitor HTMX request performance
   - Add user interaction metrics
   - Implement error rate tracking

2. **Business Logic Metrics**
   - Track sync operation success rates
   - Monitor calendar connection health
   - Add user engagement metrics
   - Create sync performance dashboards

3. **Performance Alerting**
   - Configure response time alerts
   - Add error rate threshold alerts
   - Create API quota warnings
   - Implement uptime monitoring

### Step 4: Development and Testing Performance (30 minutes)

1. **Development Performance Tools**
   - Configure Django Debug Toolbar
   - Add query count assertions
   - Implement performance test helpers
   - Create load testing scenarios

2. **Performance Regression Testing**
   - Add performance benchmarks
   - Create automated performance tests
   - Configure CI/CD performance gates
   - Implement performance budgets

## Files to Create/Modify

### Performance Monitoring Infrastructure
- `src/calendar_sync/middleware/performance.py` - Performance monitoring middleware
- `src/calendar_sync/middleware/logging.py` - Structured logging middleware
- `src/calendar_sync/metrics.py` - Metrics collection utilities
- `src/calendar_sync/monitoring.py` - Monitoring configuration

### Logging Configuration
- `src/calendar_sync/logging_config.py` - Structured logging configuration
- `src/calendar_sync/settings/monitoring.py` - Monitoring settings

### Performance Testing
- `tests/performance/` - Performance test suite
- `tests/performance/test_benchmarks.py` - Performance benchmarks
- `tests/performance/test_load.py` - Load testing scenarios

### Monitoring Dashboards
- `monitoring/dashboard.json` - Grafana dashboard configuration
- `monitoring/alerts.yml` - Alerting rules configuration

### Documentation
- `docs/MONITORING.md` - Monitoring and observability guide
- `docs/PERFORMANCE.md` - Performance optimization guide

## Code Examples

### Performance Monitoring Middleware
```python
# src/calendar_sync/middleware/performance.py
import time
import logging
import uuid
from django.utils.deprecation import MiddlewareMixin
from django.db import connection
from django.conf import settings
from typing import Callable, Optional
from .metrics import metrics_collector

logger = logging.getLogger('performance')

class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """Middleware for tracking application performance metrics"""
    
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """Start performance tracking for request"""
        # Generate correlation ID for request tracing
        correlation_id = str(uuid.uuid4())
        request.correlation_id = correlation_id
        
        # Track request start time
        request._performance_start_time = time.time()
        request._performance_start_queries = len(connection.queries)
        
        # Add correlation ID to thread-local storage for logging
        import threading
        if not hasattr(threading.current_thread(), 'correlation_id'):
            threading.current_thread().correlation_id = correlation_id
        
        return None
    
    def process_response(self, request, response):
        """Track response metrics and log performance data"""
        if not hasattr(request, '_performance_start_time'):
            return response
        
        # Calculate performance metrics
        end_time = time.time()
        response_time = end_time - request._performance_start_time
        query_count = len(connection.queries) - request._performance_start_queries
        
        # Extract request information
        method = request.method
        path = request.path
        status_code = response.status_code
        user_id = request.user.id if request.user.is_authenticated else None
        
        # Log performance data
        logger.info(
            'Request completed',
            extra={
                'correlation_id': getattr(request, 'correlation_id', None),
                'method': method,
                'path': path,
                'status_code': status_code,
                'response_time_ms': round(response_time * 1000, 2),
                'query_count': query_count,
                'user_id': user_id,
                'request_size': len(request.body) if hasattr(request, 'body') else 0,
                'response_size': len(response.content) if hasattr(response, 'content') else 0,
            }
        )
        
        # Send metrics to collector
        metrics_collector.record_request_metrics(
            method=method,
            path=path,
            status_code=status_code,
            response_time=response_time,
            query_count=query_count
        )
        
        # Check for performance issues
        self._check_performance_thresholds(
            path, response_time, query_count, request.correlation_id
        )
        
        return response
    
    def _check_performance_thresholds(
        self, 
        path: str, 
        response_time: float, 
        query_count: int, 
        correlation_id: str
    ):
        """Check if response exceeds performance thresholds"""
        
        # Response time threshold
        slow_threshold = getattr(settings, 'PERFORMANCE_SLOW_THRESHOLD', 1.0)
        if response_time > slow_threshold:
            logger.warning(
                'Slow response detected',
                extra={
                    'correlation_id': correlation_id,
                    'path': path,
                    'response_time_ms': round(response_time * 1000, 2),
                    'threshold_ms': round(slow_threshold * 1000, 2),
                }
            )
        
        # Query count threshold
        query_threshold = getattr(settings, 'PERFORMANCE_QUERY_THRESHOLD', 10)
        if query_count > query_threshold:
            logger.warning(
                'High query count detected',
                extra={
                    'correlation_id': correlation_id,
                    'path': path,
                    'query_count': query_count,
                    'threshold': query_threshold,
                }
            )

class DatabaseQueryMonitoringMiddleware(MiddlewareMixin):
    """Middleware for monitoring database query performance"""
    
    def process_response(self, request, response):
        """Log slow queries and N+1 query issues"""
        if not settings.DEBUG:
            return response
        
        correlation_id = getattr(request, 'correlation_id', None)
        slow_queries = []
        duplicate_queries = {}
        
        # Analyze queries
        for query in connection.queries:
            query_time = float(query['time'])
            query_sql = query['sql']
            
            # Check for slow queries
            if query_time > 0.1:  # 100ms threshold
                slow_queries.append({
                    'sql': query_sql[:200] + '...' if len(query_sql) > 200 else query_sql,
                    'time': query_time
                })
            
            # Check for duplicate queries (N+1 issue)
            sql_normalized = self._normalize_sql(query_sql)
            if sql_normalized in duplicate_queries:
                duplicate_queries[sql_normalized] += 1
            else:
                duplicate_queries[sql_normalized] = 1
        
        # Log slow queries
        if slow_queries:
            logger.warning(
                'Slow database queries detected',
                extra={
                    'correlation_id': correlation_id,
                    'path': request.path,
                    'slow_queries': slow_queries,
                    'total_queries': len(connection.queries)
                }
            )
        
        # Log potential N+1 issues
        n_plus_one_queries = {sql: count for sql, count in duplicate_queries.items() if count > 3}
        if n_plus_one_queries:
            logger.warning(
                'Potential N+1 query issue detected',
                extra={
                    'correlation_id': correlation_id,
                    'path': request.path,
                    'duplicate_queries': n_plus_one_queries
                }
            )
        
        return response
    
    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL query to detect duplicates"""
        import re
        # Replace parameter placeholders and values
        normalized = re.sub(r"'[^']*'", "'?'", sql)  # String literals
        normalized = re.sub(r'\b\d+\b', '?', normalized)  # Numbers
        normalized = re.sub(r'\s+', ' ', normalized)  # Whitespace
        return normalized.strip()
```

### Metrics Collection System
```python
# src/calendar_sync/metrics.py
import time
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.cache import cache
from functools import wraps

logger = logging.getLogger('metrics')

class MetricsCollector:
    """Centralized metrics collection system"""
    
    def __init__(self):
        self.enabled = getattr(settings, 'METRICS_ENABLED', True)
        self.backend = getattr(settings, 'METRICS_BACKEND', 'memory')
    
    def record_request_metrics(
        self, 
        method: str, 
        path: str, 
        status_code: int, 
        response_time: float, 
        query_count: int
    ):
        """Record HTTP request metrics"""
        if not self.enabled:
            return
        
        # Increment request counter
        self._increment_counter('http_requests_total', {
            'method': method,
            'path': self._normalize_path(path),
            'status': str(status_code)
        })
        
        # Record response time histogram
        self._record_histogram('http_request_duration_seconds', response_time, {
            'method': method,
            'path': self._normalize_path(path)
        })
        
        # Record query count
        self._record_gauge('http_request_queries', query_count, {
            'method': method,
            'path': self._normalize_path(path)
        })
    
    def record_sync_metrics(
        self, 
        calendar_id: int, 
        duration: float, 
        events_processed: int, 
        success: bool
    ):
        """Record calendar sync operation metrics"""
        if not self.enabled:
            return
        
        # Increment sync counter
        self._increment_counter('calendar_sync_total', {
            'success': str(success).lower()
        })
        
        # Record sync duration
        self._record_histogram('calendar_sync_duration_seconds', duration)
        
        # Record events processed
        self._record_histogram('calendar_sync_events_processed', events_processed)
        
        # Track sync success rate
        cache_key = f'sync_success_rate_{calendar_id}'
        success_data = cache.get(cache_key, {'total': 0, 'successful': 0})
        success_data['total'] += 1
        if success:
            success_data['successful'] += 1
        
        success_rate = success_data['successful'] / success_data['total']
        self._record_gauge('calendar_sync_success_rate', success_rate, {
            'calendar_id': str(calendar_id)
        })
        
        cache.set(cache_key, success_data, timeout=3600)  # 1 hour
    
    def record_google_api_metrics(
        self, 
        endpoint: str, 
        response_time: float, 
        status_code: int, 
        quota_used: Optional[int] = None
    ):
        """Record Google API usage metrics"""
        if not self.enabled:
            return
        
        # API request counter
        self._increment_counter('google_api_requests_total', {
            'endpoint': endpoint,
            'status': str(status_code)
        })
        
        # API response time
        self._record_histogram('google_api_duration_seconds', response_time, {
            'endpoint': endpoint
        })
        
        # Quota usage tracking
        if quota_used:
            self._record_gauge('google_api_quota_used', quota_used, {
                'endpoint': endpoint
            })
    
    def _increment_counter(self, name: str, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        if self.backend == 'memory':
            self._memory_increment_counter(name, labels or {})
        # Add other backends (Prometheus, StatsD) here
    
    def _record_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a histogram metric"""
        if self.backend == 'memory':
            self._memory_record_histogram(name, value, labels or {})
    
    def _record_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a gauge metric"""
        if self.backend == 'memory':
            self._memory_record_gauge(name, value, labels or {})
    
    def _normalize_path(self, path: str) -> str:
        """Normalize URL path for metrics (remove IDs)"""
        import re
        # Replace numeric IDs with placeholder
        path = re.sub(r'/\d+/', '/{id}/', path)
        path = re.sub(r'/\d+$', '/{id}', path)
        return path
    
    def _memory_increment_counter(self, name: str, labels: Dict[str, str]):
        """Memory-based counter implementation"""
        key = f"metric:{name}:{self._labels_to_string(labels)}"
        cache.set(key, cache.get(key, 0) + 1, timeout=None)
    
    def _memory_record_histogram(self, name: str, value: float, labels: Dict[str, str]):
        """Memory-based histogram implementation"""
        key = f"metric:{name}:histogram:{self._labels_to_string(labels)}"
        data = cache.get(key, {'values': [], 'count': 0, 'sum': 0})
        data['values'].append(value)
        data['count'] += 1
        data['sum'] += value
        
        # Keep only last 1000 values
        if len(data['values']) > 1000:
            data['values'] = data['values'][-1000:]
        
        cache.set(key, data, timeout=3600)
    
    def _memory_record_gauge(self, name: str, value: float, labels: Dict[str, str]):
        """Memory-based gauge implementation"""
        key = f"metric:{name}:gauge:{self._labels_to_string(labels)}"
        cache.set(key, value, timeout=3600)
    
    def _labels_to_string(self, labels: Dict[str, str]) -> str:
        """Convert labels dict to string for cache key"""
        return ':'.join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        # Implementation would collect all metrics from cache/backend
        # This is a simplified version
        return {
            'requests_total': cache.get('metric:http_requests_total:', 0),
            'sync_operations': cache.get('metric:calendar_sync_total:', 0),
            'api_calls': cache.get('metric:google_api_requests_total:', 0)
        }

# Global metrics collector instance
metrics_collector = MetricsCollector()

def track_performance(metric_name: str = None):
    """Decorator to track function performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                name = metric_name or f"{func.__module__}.{func.__name__}"
                
                metrics_collector._record_histogram(
                    f'function_duration_seconds',
                    duration,
                    {'function': name, 'success': str(success).lower()}
                )
        
        return wrapper
    return decorator
```

### Google API Performance Monitoring
```python
# apps/calendars/services/google_calendar_client.py - Enhanced with monitoring
from src.calendar_sync.metrics import metrics_collector, track_performance
import time

class GoogleCalendarClient:
    """Google Calendar API client with performance monitoring"""
    
    @track_performance('google_calendar.list_calendars')
    def list_calendars(self):
        """List calendars with performance tracking"""
        start_time = time.time()
        
        try:
            result = self.service.calendarList().list().execute()
            
            # Record successful API call
            metrics_collector.record_google_api_metrics(
                endpoint='calendarList.list',
                response_time=time.time() - start_time,
                status_code=200,
                quota_used=1  # Each call uses 1 quota unit
            )
            
            return result.get('items', [])
            
        except Exception as e:
            # Record failed API call
            metrics_collector.record_google_api_metrics(
                endpoint='calendarList.list',
                response_time=time.time() - start_time,
                status_code=getattr(e, 'status_code', 500)
            )
            
            logger.error(
                f"Failed to list calendars: {e}",
                extra={
                    'account_email': self.account.email,
                    'error_type': type(e).__name__,
                    'response_time': time.time() - start_time
                }
            )
            raise
    
    @track_performance('google_calendar.list_events')
    def list_events(self, calendar_id: str, sync_token: str = None):
        """List events with performance and quota monitoring"""
        start_time = time.time()
        
        try:
            request_params = {
                'calendarId': calendar_id,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            
            if sync_token:
                request_params['syncToken'] = sync_token
            
            result = self.service.events().list(**request_params).execute()
            
            events = result.get('items', [])
            
            # Record successful API call with event count
            metrics_collector.record_google_api_metrics(
                endpoint='events.list',
                response_time=time.time() - start_time,
                status_code=200,
                quota_used=1
            )
            
            # Record events fetched metric
            metrics_collector._record_histogram(
                'google_api_events_fetched',
                len(events),
                {'calendar_id': calendar_id[:10]}  # Truncate for privacy
            )
            
            return {
                'events': events,
                'next_sync_token': result.get('nextSyncToken')
            }
            
        except Exception as e:
            metrics_collector.record_google_api_metrics(
                endpoint='events.list',
                response_time=time.time() - start_time,
                status_code=getattr(e, 'status_code', 500)
            )
            raise
```

### Performance Benchmarks
```python
# tests/performance/test_benchmarks.py
import time
import pytest
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from apps.dashboard.services import DashboardService
from apps.calendars.services.calendar_service import CalendarService
from tests.conftest import BaseTestCase

class PerformanceBenchmarkTest(BaseTestCase):
    """Performance benchmark tests"""
    
    def setUp(self):
        super().setUp()
        
        # Create test data for benchmarks
        self._create_benchmark_data()
    
    def _create_benchmark_data(self):
        """Create standardized test data for benchmarks"""
        # Create 10 accounts with 5 calendars each
        for i in range(10):
            account = self.create_calendar_account(
                email=f'benchmark{i}@gmail.com',
                google_account_id=f'benchmark_account_{i}'
            )
            
            for j in range(5):
                self.create_calendar(
                    account=account,
                    name=f'Benchmark Calendar {i}_{j}',
                    google_calendar_id=f'benchmark_cal_{i}_{j}',
                    sync_enabled=j % 2 == 0
                )
    
    def test_dashboard_service_performance_benchmark(self):
        """Benchmark dashboard service performance"""
        service = DashboardService(self.user)
        
        # Warm up
        service.get_dashboard_context()
        
        # Benchmark
        start_time = time.time()
        iterations = 10
        
        for _ in range(iterations):
            context = service.get_dashboard_context()
        
        end_time = time.time()
        average_time = (end_time - start_time) / iterations
        
        # Assert performance target
        self.assertLess(
            average_time, 0.1,  # 100ms target
            f"Dashboard service average time {average_time:.3f}s exceeds 100ms target"
        )
        
        # Verify data correctness
        self.assertEqual(len(context['calendar_accounts']), 10)
        self.assertEqual(context['total_calendars'], 50)
    
    def test_calendar_service_bulk_operations_benchmark(self):
        """Benchmark bulk calendar operations"""
        from apps.calendars.models import Calendar
        
        service = CalendarService(self.user)
        calendar_ids = list(Calendar.objects.for_user(self.user).values_list('id', flat=True))
        
        # Benchmark bulk toggle
        start_time = time.time()
        
        result = service.bulk_toggle_calendars(calendar_ids, enable=True)
        
        end_time = time.time()
        
        # Assert performance and correctness
        self.assertLess(end_time - start_time, 1.0)  # 1 second target
        self.assertEqual(len(result), len(calendar_ids))
    
    @pytest.mark.slow
    def test_view_response_time_benchmarks(self):
        """Benchmark key view response times"""
        from django.test import Client
        
        client = Client()
        client.login(username='testuser', password='testpass123')
        
        views_to_test = [
            ('dashboard:index', {}),
            ('dashboard:account_detail', {'account_id': self.create_calendar_account().id}),
        ]
        
        for view_name, kwargs in views_to_test:
            with self.subTest(view=view_name):
                from django.urls import reverse
                url = reverse(view_name, kwargs=kwargs)
                
                # Warm up
                client.get(url)
                
                # Benchmark
                start_time = time.time()
                response = client.get(url)
                end_time = time.time()
                
                response_time = end_time - start_time
                
                self.assertEqual(response.status_code, 200)
                self.assertLess(
                    response_time, 0.5,  # 500ms target
                    f"View {view_name} took {response_time:.3f}s, exceeds 500ms target"
                )

class LoadTestScenarios(TestCase):
    """Load testing scenarios"""
    
    @pytest.mark.load_test
    def test_concurrent_dashboard_access(self):
        """Test dashboard under concurrent load"""
        import threading
        import queue
        
        def dashboard_request(result_queue):
            """Single dashboard request thread"""
            client = Client()
            client.login(username='testuser', password='testpass123')
            
            start_time = time.time()
            response = client.get('/dashboard/')
            end_time = time.time()
            
            result_queue.put({
                'status_code': response.status_code,
                'response_time': end_time - start_time
            })
        
        # Run 10 concurrent requests
        result_queue = queue.Queue()
        threads = []
        
        for _ in range(10):
            thread = threading.Thread(target=dashboard_request, args=(result_queue,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Analyze results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())
        
        # Assert all succeeded
        for result in results:
            self.assertEqual(result['status_code'], 200)
        
        # Check response time distribution
        response_times = [r['response_time'] for r in results]
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        self.assertLess(avg_response_time, 1.0)  # Average under 1 second
        self.assertLess(max_response_time, 2.0)  # Max under 2 seconds
```

## Testing Requirements

### Performance Tests
- Response time benchmarks for all key views
- Database query performance validation
- Load testing for concurrent users
- Memory usage profiling

### Monitoring Validation
- Metrics collection accuracy
- Alert threshold testing
- Dashboard functionality
- Log correlation verification

### Integration Tests
- End-to-end monitoring workflow
- Alert delivery testing
- Performance regression detection

## Definition of Done

- [ ] APM middleware implemented and tested
- [ ] Database query monitoring active
- [ ] Google API usage tracked and alerted
- [ ] Structured logging with correlation IDs
- [ ] Performance metrics dashboard created
- [ ] Load testing framework established
- [ ] Performance budgets defined and enforced
- [ ] Production monitoring configured
- [ ] Alert thresholds tuned and tested
- [ ] Documentation completed

## Success Metrics

- Response time P95 ≤500ms for key endpoints
- Database query count ≤5 per request average
- Google API quota usage tracked and under limits
- Error rate ≤1% for production traffic
- Performance regression detection within 1 hour
- Alert response time ≤5 minutes for critical issues

This task provides comprehensive observability and performance monitoring to ensure optimal application performance in production.