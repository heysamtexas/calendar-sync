"""
UUID Correlation Utilities for Bulletproof Event Tracking

Guilfoyle's triple-redundancy strategy:
1. Primary: ExtendedProperties (most reliable)
2. Backup 1: HTML comment in description (user-invisible)  
3. Backup 2: Zero-width characters in title (invisible but detectable)
"""

import re
import uuid
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class UUIDCorrelationUtils:
    """Triple-redundancy UUID utilities for bulletproof event detection"""
    
    # UUID patterns for different embedding methods
    EXTENDED_PROPERTIES_KEY = 'calendar_bridge_uuid'
    HTML_COMMENT_PATTERN = r'<!-- \[CB:([a-f0-9-]{36})\] -->'
    ZERO_WIDTH_PATTERN = r'\u200B([a-f0-9-]{36})\u200B'
    
    @classmethod
    def embed_uuid_in_event(
        cls, 
        event_data: Dict[str, Any], 
        correlation_uuid: str,
        skip_title_embedding: bool = False
    ) -> Dict[str, Any]:
        """
        Embed UUID using triple-redundancy strategy
        
        Guilfoyle's approach: Three different methods so detection never fails
        
        Args:
            skip_title_embedding: If True, skip zero-width title embedding (for busy blocks)
        """
        # Validate UUID format
        try:
            uuid.UUID(correlation_uuid)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {correlation_uuid}")
        
        # Method 1: ExtendedProperties (primary, most reliable)
        cls._embed_in_extended_properties(event_data, correlation_uuid)
        
        # Method 2: HTML comment in description (backup 1)
        cls._embed_in_description(event_data, correlation_uuid)
        
        # Method 3: Zero-width characters in title (backup 2) - SKIP for busy blocks
        if not skip_title_embedding:
            cls._embed_in_title(event_data, correlation_uuid)
        
        return event_data
    
    @classmethod
    def _embed_in_extended_properties(cls, event_data: Dict[str, Any], correlation_uuid: str):
        """Embed UUID in ExtendedProperties (primary method)"""
        if 'extendedProperties' not in event_data:
            event_data['extendedProperties'] = {}
        if 'private' not in event_data['extendedProperties']:
            event_data['extendedProperties']['private'] = {}
        
        event_data['extendedProperties']['private'][cls.EXTENDED_PROPERTIES_KEY] = correlation_uuid
    
    @classmethod
    def _embed_in_description(cls, event_data: Dict[str, Any], correlation_uuid: str):
        """Embed UUID in description as HTML comment (backup method 1)"""
        description = event_data.get('description', '')
        marker = f'<!-- [CB:{correlation_uuid}] -->'
        
        # Only add if not already present
        if marker not in description:
            # Add to end of description, separated by newline if description exists
            if description:
                event_data['description'] = f"{description}\n{marker}"
            else:
                event_data['description'] = marker
    
    @classmethod
    def _embed_in_title(cls, event_data: Dict[str, Any], correlation_uuid: str):
        """Embed UUID using zero-width characters in title (backup method 2)"""
        title = event_data.get('summary', '')
        marker = f'\u200B{correlation_uuid}\u200B'  # Zero-width space markers
        
        # Only add if not already present
        if marker not in title:
            # Add at the end of title (invisible to users)
            event_data['summary'] = f"{title}{marker}"
    
    @classmethod
    def extract_uuid_from_event(cls, google_event: Dict[str, Any]) -> Optional[str]:
        """
        Extract UUID using all three methods (try primary first, fallback to others)
        
        Returns the first UUID found, or None if no UUID detected
        """
        # Method 1: Try ExtendedProperties first (most reliable)
        correlation_uuid = cls._extract_from_extended_properties(google_event)
        if correlation_uuid:
            return correlation_uuid
        
        # Method 2: Try description HTML comment
        correlation_uuid = cls._extract_from_description(google_event)
        if correlation_uuid:
            logger.info(f"UUID extracted from description fallback: {correlation_uuid}")
            return correlation_uuid
        
        # Method 3: Try zero-width characters in title
        correlation_uuid = cls._extract_from_title(google_event)
        if correlation_uuid:
            logger.info(f"UUID extracted from title fallback: {correlation_uuid}")
            return correlation_uuid
        
        # No UUID found in any method
        return None
    
    @classmethod
    def _extract_from_extended_properties(cls, google_event: Dict[str, Any]) -> Optional[str]:
        """Extract UUID from ExtendedProperties"""
        try:
            extended = google_event.get('extendedProperties', {})
            private_props = extended.get('private', {})
            correlation_uuid = private_props.get(cls.EXTENDED_PROPERTIES_KEY)
            
            if correlation_uuid:
                # Validate UUID format
                uuid.UUID(correlation_uuid)
                return correlation_uuid
        except (ValueError, KeyError, TypeError):
            pass
        return None
    
    @classmethod
    def _extract_from_description(cls, google_event: Dict[str, Any]) -> Optional[str]:
        """Extract UUID from description HTML comment"""
        try:
            description = google_event.get('description', '')
            if description:
                match = re.search(cls.HTML_COMMENT_PATTERN, description)
                if match:
                    correlation_uuid = match.group(1)
                    # Validate UUID format
                    uuid.UUID(correlation_uuid)
                    return correlation_uuid
        except (ValueError, TypeError):
            pass
        return None
    
    @classmethod
    def _extract_from_title(cls, google_event: Dict[str, Any]) -> Optional[str]:
        """Extract UUID from title zero-width characters"""
        try:
            title = google_event.get('summary', '')
            if title:
                match = re.search(cls.ZERO_WIDTH_PATTERN, title)
                if match:
                    correlation_uuid = match.group(1)
                    # Validate UUID format
                    uuid.UUID(correlation_uuid)
                    return correlation_uuid
        except (ValueError, TypeError):
            pass
        return None
    
    @classmethod
    def is_our_event(cls, google_event: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Check if event belongs to us and return UUID
        
        Returns (is_ours, uuid) tuple
        """
        correlation_uuid = cls.extract_uuid_from_event(google_event)
        
        if not correlation_uuid:
            return False, None
        
        # Check if UUID exists in our EventState table
        try:
            from apps.calendars.models import EventState
            
            event_state = EventState.objects.by_uuid(correlation_uuid)
            is_ours = event_state is not None and event_state.is_busy_block
            
            return is_ours, correlation_uuid
            
        except Exception as e:
            logger.error(f"Error checking event ownership for UUID {correlation_uuid}: {e}")
            return False, correlation_uuid
    
    @classmethod
    def clean_title_for_display(cls, title: str) -> str:
        """Remove invisible UUID markers from title for display purposes"""
        if not title:
            return title
        
        # Remove zero-width characters and UUIDs
        cleaned = re.sub(cls.ZERO_WIDTH_PATTERN, '', title)
        return cleaned.strip()
    
    @classmethod
    def clean_description_for_display(cls, description: str) -> str:
        """Remove HTML comment UUID markers from description for display purposes"""
        if not description:
            return description
        
        # Remove HTML comment markers
        cleaned = re.sub(cls.HTML_COMMENT_PATTERN, '', description)
        return cleaned.strip()
    
    @classmethod
    def validate_event_integrity(cls, google_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that all three UUID embedding methods are consistent
        
        Returns validation report with any inconsistencies found
        """
        report = {
            'consistent': True,
            'primary_uuid': None,
            'backup1_uuid': None, 
            'backup2_uuid': None,
            'issues': []
        }
        
        # Extract from all three methods
        report['primary_uuid'] = cls._extract_from_extended_properties(google_event)
        report['backup1_uuid'] = cls._extract_from_description(google_event)
        report['backup2_uuid'] = cls._extract_from_title(google_event)
        
        # Check for consistency
        uuids = [
            report['primary_uuid'], 
            report['backup1_uuid'], 
            report['backup2_uuid']
        ]
        unique_uuids = set(uuid for uuid in uuids if uuid is not None)
        
        if len(unique_uuids) > 1:
            report['consistent'] = False
            report['issues'].append(f"Inconsistent UUIDs found: {unique_uuids}")
        
        # Check for missing primary method
        if not report['primary_uuid'] and (report['backup1_uuid'] or report['backup2_uuid']):
            report['consistent'] = False
            report['issues'].append("Primary UUID (ExtendedProperties) missing but backup methods present")
        
        return report


class LegacyDetectionUtils:
    """
    Legacy text-based detection utilities for transition period
    
    Provides fallback detection for events created before UUID correlation
    """
    
    @classmethod
    def is_legacy_busy_block(cls, google_event: Dict[str, Any]) -> bool:
        """Detect legacy busy blocks using old text-based patterns"""
        title = google_event.get('summary', '')
        description = google_event.get('description', '')
        
        # Legacy patterns from old BusyBlock.is_system_busy_block()
        legacy_patterns = [
            'Busy - ',           # Clean title prefix
            '🔒 Busy - ',       # Emoji prefix (if still present)
            'CalSync [source:',  # Legacy description pattern
        ]
        
        for pattern in legacy_patterns:
            if pattern in title or pattern in description:
                return True
        
        return False
    
    @classmethod
    def upgrade_legacy_event(cls, google_event: Dict[str, Any], correlation_uuid: str) -> Dict[str, Any]:
        """
        Upgrade legacy event to UUID correlation system
        
        Adds UUID markers while preserving existing content
        """
        logger.info(f"Upgrading legacy event {google_event.get('id')} to UUID correlation")
        
        # Use triple-redundancy embedding
        return UUIDCorrelationUtils.embed_uuid_in_event(
            event_data=google_event,
            correlation_uuid=correlation_uuid
        )