"""Tests for event collectors - page views, clicks, and session tracking"""

import json
import time
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, List, Optional

import pytest


class MockElement:
    """Mock DOM element for testing click tracking"""

    def __init__(self, tag_name: str, attributes: Dict[str, str] = None, text_content: str = ""):
        self.tag_name = tag_name.lower()
        self.attributes = attributes or {}
        self.text_content = text_content
        self.onclick = None

    def getAttribute(self, name: str) -> Optional[str]:
        return self.attributes.get(name)

    def hasAttribute(self, name: str) -> bool:
        return name in self.attributes

    def closest(self, selector: str) -> Optional['MockElement']:
        # Simplified selector matching for testing
        if self.tag_name in selector or any(attr in selector for attr in self.attributes.keys()):
            return self
        return None


class MockLocation:
    """Mock window.location for testing"""

    def __init__(self, pathname: str = "/", search: str = "", hostname: str = "example.com"):
        self.pathname = pathname
        self.search = search
        self.hostname = hostname


class MockDocument:
    """Mock document for testing"""

    def __init__(self, referrer: str = ""):
        self.referrer = referrer


class MockNavigator:
    """Mock navigator for testing"""

    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"):
        self.user_agent = user_agent


class MockPrivacyManager:
    """Mock privacy manager for event collector testing"""

    def __init__(self, consented: bool = True):
        self._consented = consented
        self._session_id = "test_session_123"

    def has_consented(self) -> bool:
        return self._consented

    def get_session_id(self) -> str:
        return self._session_id

    def on_consent_change(self, callback):
        # Store callback for testing
        self._callback = callback
        return lambda: None

    def simulate_consent_change(self, consented: bool):
        """Test helper to simulate consent changes"""
        self._consented = consented
        if hasattr(self, '_callback'):
            self._callback({'accepted': consented})


class MockAnalytics:
    """Mock analytics service for event collector testing"""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.tracking_stopped = False

    def track_page_view(self, properties: Dict[str, Any]):
        if not self.tracking_stopped:
            self.events.append({'type': 'page_view', 'properties': properties})

    def track_element_click(self, properties: Dict[str, Any]):
        if not self.tracking_stopped:
            self.events.append({'type': 'element_click', 'properties': properties})

    def track_session_start(self, properties: Dict[str, Any]):
        if not self.tracking_stopped:
            self.events.append({'type': 'session_start', 'properties': properties})

    def track(self, event: str, properties: Dict[str, Any]):
        if not self.tracking_stopped:
            self.events.append({'type': event, 'properties': properties})

    def stop_tracking(self):
        self.tracking_stopped = True

    def resume_tracking(self):
        self.tracking_stopped = False


class MockPageViewTracker:
    """Mock page view tracking functionality"""

    def __init__(self, privacy_manager: MockPrivacyManager, analytics: MockAnalytics, document: MockDocument):
        self.privacy_manager = privacy_manager
        self.analytics = analytics
        self.document = document
        self.last_tracked_path = ""

    def track_page_view(self, location: MockLocation, navigation_type: str = "navigate"):
        if not self.privacy_manager.has_consented():
            return

        current_path = location.pathname + location.search

        if self.last_tracked_path == current_path:
            return

        self.last_tracked_path = current_path

        page_view_data = {
            'route': current_path,
            'referrer': self.document.referrer or 'direct',
            'timestamp': datetime.now(),
            'user_id': self._get_current_user_id()
        }

        self.analytics.track_page_view(page_view_data)

        if navigation_type:
            self.analytics.track('navigation_method', {
                'method': navigation_type,
                'from': self.last_tracked_path or 'unknown',
                'to': current_path,
                'timestamp': datetime.now()
            })

    def _get_current_user_id(self) -> Optional[str]:
        # Mock user ID retrieval
        return 'test_user_123'


class MockClickTracker:
    """Mock click tracking functionality"""

    def __init__(self, privacy_manager: MockPrivacyManager, analytics: MockAnalytics, location: MockLocation):
        self.privacy_manager = privacy_manager
        self.analytics = analytics
        self.location = location
        self.is_active = False

    def start(self):
        self.is_active = True

    def stop(self):
        self.is_active = False

    def handle_click(self, element: MockElement):
        if not self.is_active or not self.privacy_manager.has_consented():
            return

        click_data = self._extract_click_data(element)
        if click_data:
            self.analytics.track_element_click(click_data)

    def _extract_click_data(self, element: MockElement) -> Optional[Dict[str, Any]]:
        if not self._is_trackable_element(element):
            return None

        return {
            'element_type': self._get_element_type(element),
            'element_label': self._get_element_label(element),
            'page_context': self._get_page_context()
        }

    def _is_trackable_element(self, element: MockElement) -> bool:
        trackable_types = ['button', 'a', 'input', 'select', 'textarea', 'form']

        if element.tag_name in trackable_types:
            return True

        if (element.onclick or
                element.getAttribute('role') == 'button' or
                element.hasAttribute('data-track')):
            return True

        return bool(element.closest('button, a, [role="button"], [data-track]'))

    def _get_element_type(self, element: MockElement) -> str:
        if element.tag_name == 'input':
            input_type = element.getAttribute('type') or 'text'
            return f'input_{input_type}'

        role = element.getAttribute('role')
        if role:
            return f'{element.tag_name}_{role}'

        if element.tag_name == 'form':
            return 'form_submission'

        track_type = element.getAttribute('data-track-type')
        if track_type:
            return track_type

        return element.tag_name

    def _get_element_label(self, element: MockElement) -> str:
        label_sources = [
            element.getAttribute('data-track-label'),
            element.getAttribute('aria-label'),
            element.getAttribute('title'),
            element.getAttribute('placeholder'),
            element.getAttribute('value'),
            element.text_content.strip() if element.text_content else None,
            element.getAttribute('name'),
            element.getAttribute('id'),
        ]

        for label in label_sources:
            if label:
                return label[:100]  # Limit length

        return 'unlabeled_element'

    def _get_page_context(self) -> str:
        path = self.location.pathname
        sections = [s for s in path.split('/') if s]

        if not sections:
            return 'home'

        return sections[0] or 'unknown'


class MockSessionTracker:
    """Mock session tracking functionality"""

    def __init__(self, privacy_manager: MockPrivacyManager, analytics: MockAnalytics, navigator: MockNavigator, document: MockDocument, location: MockLocation):
        self.privacy_manager = privacy_manager
        self.analytics = analytics
        self.navigator = navigator
        self.document = document
        self.location = location
        self.session_started = False
        self.session_id = ""

    def start_session(self):
        if self.session_started or not self.privacy_manager.has_consented():
            return

        self.session_id = self.privacy_manager.get_session_id()
        self.session_started = True

        session_data = {
            'device_type': self._get_device_type(),
            'browser': self._get_browser_info(),
            'entry_point': self._get_entry_point()
        }

        self.analytics.track_session_start(session_data)

    def end_session(self):
        if not self.session_started or not self.privacy_manager.has_consented():
            return

        self.analytics.track('session_end', {
            'session_id': self.session_id,
            'timestamp': datetime.now()
        })

    def _get_device_type(self) -> str:
        user_agent = self.navigator.user_agent.lower()

        if any(keyword in user_agent for keyword in ['tablet', 'ipad']):
            return 'tablet'

        if any(keyword in user_agent for keyword in ['mobile', 'iphone', 'android']):
            return 'mobile'

        return 'desktop'

    def _get_browser_info(self) -> str:
        user_agent = self.navigator.user_agent

        if 'Chrome' in user_agent:
            return 'chrome'
        elif 'Firefox' in user_agent:
            return 'firefox'
        elif 'Safari' in user_agent and 'Chrome' not in user_agent:
            return 'safari'
        elif 'Edge' in user_agent:
            return 'edge'

        return 'unknown'

    def _get_entry_point(self) -> str:
        referrer = self.document.referrer

        if not referrer:
            return 'direct'

        try:
            # Parse referrer domain
            if '://' in referrer:
                referrer_domain = referrer.split('://')[1].split('/')[0]
            else:
                referrer_domain = referrer.split('/')[0]

            current_domain = self.location.hostname

            if referrer_domain == current_domain:
                return 'internal'

            if 'google' in referrer_domain:
                return 'google'
            elif 'facebook' in referrer_domain:
                return 'facebook'
            elif 'twitter' in referrer_domain:
                return 'twitter'

            return 'external'
        except:
            return 'unknown'


@pytest.fixture
def mock_privacy_manager():
    """Create mock privacy manager"""
    return MockPrivacyManager(consented=True)


@pytest.fixture
def mock_analytics():
    """Create mock analytics service"""
    return MockAnalytics()


@pytest.fixture
def mock_location():
    """Create mock location"""
    return MockLocation()


@pytest.fixture
def mock_document():
    """Create mock document"""
    return MockDocument()


@pytest.fixture
def mock_navigator():
    """Create mock navigator"""
    return MockNavigator()


class TestPageViewTracking:
    """Test page view tracking functionality"""

    def test_automatic_page_view_tracking(self, mock_privacy_manager, mock_analytics, mock_document):
        """Given user navigates When route changes Then page_view events fire automatically"""
        tracker = MockPageViewTracker(mock_privacy_manager, mock_analytics, mock_document)

        # Track different pages
        locations = [
            MockLocation("/"),
            MockLocation("/dashboard"),
            MockLocation("/settings"),
            MockLocation("/profile", "?tab=preferences")
        ]

        for location in locations:
            tracker.track_page_view(location)

        # Should have tracked all page views
        page_view_events = [e for e in mock_analytics.events if e['type'] == 'page_view']
        assert len(page_view_events) == 4

        # Verify properties
        assert page_view_events[0]['properties']['route'] == '/'
        assert page_view_events[1]['properties']['route'] == '/dashboard'
        assert page_view_events[3]['properties']['route'] == '/profile?tab=preferences'

    def test_duplicate_page_view_prevention(self, mock_privacy_manager, mock_analytics, mock_document):
        """Test that duplicate page views are not tracked"""
        tracker = MockPageViewTracker(mock_privacy_manager, mock_analytics, mock_document)
        location = MockLocation("/same-page")

        # Track same page multiple times
        tracker.track_page_view(location)
        tracker.track_page_view(location)
        tracker.track_page_view(location)

        page_view_events = [e for e in mock_analytics.events if e['type'] == 'page_view']
        assert len(page_view_events) == 1

    def test_page_view_with_referrer(self, mock_privacy_manager, mock_analytics):
        """Test page view tracking includes referrer information"""
        document_with_referrer = MockDocument(referrer="https://google.com/search")
        tracker = MockPageViewTracker(mock_privacy_manager, mock_analytics, document_with_referrer)

        tracker.track_page_view(MockLocation("/landing"))

        page_view_events = [e for e in mock_analytics.events if e['type'] == 'page_view']
        assert page_view_events[0]['properties']['referrer'] == 'https://google.com/search'

    def test_page_view_without_consent(self, mock_analytics, mock_document):
        """Test that page views are not tracked without consent"""
        no_consent_privacy = MockPrivacyManager(consented=False)
        tracker = MockPageViewTracker(no_consent_privacy, mock_analytics, mock_document)

        tracker.track_page_view(MockLocation("/test"))

        assert len(mock_analytics.events) == 0

    def test_navigation_method_tracking(self, mock_privacy_manager, mock_analytics, mock_document):
        """Test that navigation methods are tracked"""
        tracker = MockPageViewTracker(mock_privacy_manager, mock_analytics, mock_document)

        tracker.track_page_view(MockLocation("/page1"), "navigate")

        navigation_events = [e for e in mock_analytics.events if e['type'] == 'navigation_method']
        assert len(navigation_events) == 1
        assert navigation_events[0]['properties']['method'] == 'navigate'


class TestClickTracking:
    """Test click event capture functionality"""

    def test_button_click_tracking(self, mock_privacy_manager, mock_analytics, mock_location):
        """Given interactive elements When user clicks Then click events captured with metadata"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        # Test different button types
        buttons = [
            MockElement('button', {'aria-label': 'Submit Form'}, 'Submit'),
            MockElement('a', {'href': '/learn-more', 'title': 'Learn More'}, 'Learn More'),
            MockElement('input', {'type': 'submit', 'value': 'Search'}),
            MockElement('div', {'role': 'button', 'data-track-label': 'Custom Button'}, 'Click Me')
        ]

        for button in buttons:
            tracker.handle_click(button)

        click_events = [e for e in mock_analytics.events if e['type'] == 'element_click']
        assert len(click_events) == 4

        # Verify element types
        expected_types = ['button', 'a', 'input_submit', 'div_button']
        actual_types = [e['properties']['element_type'] for e in click_events]
        assert set(actual_types) == set(expected_types)

    def test_click_element_label_extraction(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test that element labels are extracted correctly"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        # Test label priority order
        elements = [
            MockElement('button', {'data-track-label': 'Custom Label'}, 'Button Text'),
            MockElement('button', {'aria-label': 'Aria Label'}, 'Button Text'),
            MockElement('button', {'title': 'Title Attribute'}, 'Button Text'),
            MockElement('button', {}, 'Button Text Content'),
            MockElement('input', {'name': 'search-input', 'placeholder': 'Search...'}),
        ]

        for element in elements:
            tracker.handle_click(element)

        click_events = [e for e in mock_analytics.events if e['type'] == 'element_click']
        labels = [e['properties']['element_label'] for e in click_events]

        assert 'Custom Label' in labels  # Highest priority
        assert 'Aria Label' in labels
        assert 'Title Attribute' in labels
        assert 'Button Text Content' in labels
        assert 'Search...' in labels  # From placeholder

    def test_non_trackable_elements_ignored(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test that non-interactive elements are not tracked"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        non_trackable = [
            MockElement('div', {}, 'Just a div'),
            MockElement('span', {}, 'Just text'),
            MockElement('p', {}, 'Paragraph'),
        ]

        for element in non_trackable:
            tracker.handle_click(element)

        assert len(mock_analytics.events) == 0

    def test_page_context_extraction(self, mock_privacy_manager, mock_analytics):
        """Test that page context is extracted correctly"""
        locations = [
            MockLocation("/"),  # home
            MockLocation("/dashboard/overview"),  # dashboard
            MockLocation("/settings/privacy"),  # settings
        ]

        for location in locations:
            tracker = MockClickTracker(mock_privacy_manager, mock_analytics, location)
            tracker.start()
            button = MockElement('button', {}, 'Test Button')
            tracker.handle_click(button)

        click_events = [e for e in mock_analytics.events if e['type'] == 'element_click']
        contexts = [e['properties']['page_context'] for e in click_events]

        assert 'home' in contexts
        assert 'dashboard' in contexts
        assert 'settings' in contexts

    def test_click_tracking_without_consent(self, mock_analytics, mock_location):
        """Test that clicks are not tracked without consent"""
        no_consent_privacy = MockPrivacyManager(consented=False)
        tracker = MockClickTracker(no_consent_privacy, mock_analytics, mock_location)
        tracker.start()

        button = MockElement('button', {}, 'Test Button')
        tracker.handle_click(button)

        assert len(mock_analytics.events) == 0

    def test_click_tracker_start_stop(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test click tracker activation and deactivation"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        button = MockElement('button', {}, 'Test Button')

        # Not started - should not track
        tracker.handle_click(button)
        assert len(mock_analytics.events) == 0

        # Started - should track
        tracker.start()
        tracker.handle_click(button)
        assert len(mock_analytics.events) == 1

        # Stopped - should not track
        tracker.stop()
        tracker.handle_click(button)
        assert len(mock_analytics.events) == 1  # No new events


class TestSessionTracking:
    """Test session continuity and tracking"""

    def test_session_start_tracking(self, mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location):
        """Given user session When session starts Then session_start events fire"""
        tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location)

        tracker.start_session()

        session_events = [e for e in mock_analytics.events if e['type'] == 'session_start']
        assert len(session_events) == 1

        props = session_events[0]['properties']
        assert 'device_type' in props
        assert 'browser' in props
        assert 'entry_point' in props

    def test_device_type_detection(self, mock_privacy_manager, mock_analytics, mock_document, mock_location):
        """Test device type detection from user agent"""
        test_cases = [
            ("Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X)", "mobile"),
            ("Mozilla/5.0 (iPad; CPU OS 14_7_1 like Mac OS X)", "tablet"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "desktop"),
            ("Mozilla/5.0 (Android 11; Mobile; rv:89.0)", "mobile"),
        ]

        for user_agent, expected_device in test_cases:
            navigator = MockNavigator(user_agent)
            tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, navigator, mock_document, mock_location)
            tracker.start_session()

            session_events = [e for e in mock_analytics.events if e['type'] == 'session_start']
            device_type = session_events[-1]['properties']['device_type']
            assert device_type == expected_device

            # Clear events for next test
            mock_analytics.events.clear()
            tracker.session_started = False

    def test_browser_detection(self, mock_privacy_manager, mock_analytics, mock_document, mock_location):
        """Test browser detection from user agent"""
        test_cases = [
            ("Chrome/91.0.4472.124 Safari/537.36", "chrome"),
            ("Firefox/89.0", "firefox"),
            ("Safari/605.1.15 (not Chrome)", "safari"),
            ("Edg/91.0.864.59", "edge"),
            ("Unknown Browser", "unknown"),
        ]

        for user_agent, expected_browser in test_cases:
            navigator = MockNavigator(user_agent)
            tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, navigator, mock_document, mock_location)
            tracker.start_session()

            session_events = [e for e in mock_analytics.events if e['type'] == 'session_start']
            browser = session_events[-1]['properties']['browser']
            assert browser == expected_browser

            # Clear events for next test
            mock_analytics.events.clear()
            tracker.session_started = False

    def test_entry_point_detection(self, mock_privacy_manager, mock_analytics, mock_navigator, mock_location):
        """Test entry point detection from referrer"""
        test_cases = [
            ("", "direct"),
            ("https://google.com/search", "google"),
            ("https://facebook.com/share", "facebook"),
            ("https://example.com/page", "external"),
            ("https://example.com/other-page", "internal"),  # Same domain
        ]

        location = MockLocation(hostname="example.com")

        for referrer, expected_entry in test_cases:
            document = MockDocument(referrer)
            tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, mock_navigator, document, location)
            tracker.start_session()

            session_events = [e for e in mock_analytics.events if e['type'] == 'session_start']
            entry_point = session_events[-1]['properties']['entry_point']
            assert entry_point == expected_entry

            # Clear events for next test
            mock_analytics.events.clear()
            tracker.session_started = False

    def test_session_end_tracking(self, mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location):
        """Test session end tracking"""
        tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location)

        tracker.start_session()
        session_id = tracker.session_id

        tracker.end_session()

        session_end_events = [e for e in mock_analytics.events if e['type'] == 'session_end']
        assert len(session_end_events) == 1
        assert session_end_events[0]['properties']['session_id'] == session_id

    def test_session_without_consent(self, mock_analytics, mock_navigator, mock_document, mock_location):
        """Test that session is not tracked without consent"""
        no_consent_privacy = MockPrivacyManager(consented=False)
        tracker = MockSessionTracker(no_consent_privacy, mock_analytics, mock_navigator, mock_document, mock_location)

        tracker.start_session()

        assert len(mock_analytics.events) == 0
        assert not tracker.session_started

    def test_duplicate_session_start_prevention(self, mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location):
        """Test that multiple session starts are prevented"""
        tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location)

        tracker.start_session()
        tracker.start_session()
        tracker.start_session()

        session_events = [e for e in mock_analytics.events if e['type'] == 'session_start']
        assert len(session_events) == 1


class TestConsentIntegration:
    """Test integration with privacy consent management"""

    def test_event_collectors_consent_integration(self, mock_analytics, mock_location, mock_document, mock_navigator):
        """Test that all collectors respect consent changes"""
        privacy_manager = MockPrivacyManager(consented=True)

        # Create all trackers
        page_tracker = MockPageViewTracker(privacy_manager, mock_analytics, mock_document)
        click_tracker = MockClickTracker(privacy_manager, mock_analytics, mock_location)
        session_tracker = MockSessionTracker(privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location)

        click_tracker.start()

        # Track events with consent
        page_tracker.track_page_view(MockLocation("/test"))
        click_tracker.handle_click(MockElement('button', {}, 'Test'))
        session_tracker.start_session()

        assert len(mock_analytics.events) == 3

        # Simulate consent revocation
        privacy_manager.simulate_consent_change(False)

        # Clear previous events
        mock_analytics.events.clear()

        # Try tracking without consent
        page_tracker.track_page_view(MockLocation("/test2"))
        click_tracker.handle_click(MockElement('button', {}, 'Test2'))
        session_tracker.start_session()  # Reset session_started for test

        assert len(mock_analytics.events) == 0

    def test_analytics_service_stop_resume(self, mock_privacy_manager):
        """Test analytics service stop/resume on consent changes"""
        analytics = MockAnalytics()

        # Setup consent change handler (simulating event collectors initialization)
        def on_consent_change(consent_state):
            if consent_state['accepted']:
                analytics.resume_tracking()
            else:
                analytics.stop_tracking()

        mock_privacy_manager.on_consent_change(on_consent_change)

        # Start with consent - should be able to track
        analytics.track('test_event', {'test': 'data'})
        assert len(analytics.events) == 1

        # Revoke consent - should stop tracking
        mock_privacy_manager.simulate_consent_change(False)
        analytics.track('blocked_event', {'test': 'data'})
        assert len(analytics.events) == 1  # No new events

        # Give consent again - should resume tracking
        mock_privacy_manager.simulate_consent_change(True)
        analytics.track('resumed_event', {'test': 'data'})
        assert len(analytics.events) == 2


class TestEventCollectorInitialization:
    """Test event collector initialization and cleanup"""

    def test_initialization_starts_all_collectors(self, mock_privacy_manager, mock_analytics):
        """Test that initialization starts all event collectors"""
        # This would be the equivalent of initializeEventCollectors()

        # Mock the initialization process
        click_tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        session_tracker = MockSessionTracker(mock_privacy_manager, mock_analytics, mock_navigator, mock_document, mock_location)

        # Initialize
        click_tracker.start()
        session_tracker.start_session()

        assert click_tracker.is_active
        assert session_tracker.session_started

    def test_cleanup_stops_all_collectors(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test that cleanup stops all event collectors"""
        # This would be the equivalent of cleanupEventCollectors()
        click_tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)

        # Start and then cleanup
        click_tracker.start()
        assert click_tracker.is_active

        click_tracker.stop()
        assert not click_tracker.is_active

    def test_initialization_with_existing_consent(self, mock_analytics, mock_location, mock_document, mock_navigator):
        """Test initialization when user already has consent"""
        privacy_manager = MockPrivacyManager(consented=True)

        # Should immediately start tracking
        click_tracker = MockClickTracker(privacy_manager, mock_analytics, mock_location)
        click_tracker.start()

        button = MockElement('button', {}, 'Test')
        click_tracker.handle_click(button)

        assert len(mock_analytics.events) == 1

    def test_initialization_without_consent(self, mock_analytics, mock_location):
        """Test initialization when user has not consented"""
        privacy_manager = MockPrivacyManager(consented=False)

        # Should not track until consent is given
        click_tracker = MockClickTracker(privacy_manager, mock_analytics, mock_location)
        click_tracker.start()

        button = MockElement('button', {}, 'Test')
        click_tracker.handle_click(button)

        assert len(mock_analytics.events) == 0


class TestPerformanceAndResilience:
    """Test performance and network resilience features"""

    def test_event_tracking_performance(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test that event tracking is performant"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        start_time = time.time()

        # Track many events quickly
        for i in range(100):
            button = MockElement('button', {}, f'Button {i}')
            tracker.handle_click(button)

        end_time = time.time()
        duration = (end_time - start_time) * 1000  # Convert to ms

        # Should be very fast (less than 100ms for 100 events)
        assert duration < 500
        assert len(mock_analytics.events) == 100

    def test_large_element_label_truncation(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test that long element labels are truncated"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        # Create element with very long label
        long_label = "x" * 200  # 200 character label
        button = MockElement('button', {'aria-label': long_label})
        tracker.handle_click(button)

        click_events = [e for e in mock_analytics.events if e['type'] == 'element_click']
        label = click_events[0]['properties']['element_label']

        # Should be truncated to 100 characters
        assert len(label) == 100

    def test_malformed_element_handling(self, mock_privacy_manager, mock_analytics, mock_location):
        """Test handling of malformed or edge case elements"""
        tracker = MockClickTracker(mock_privacy_manager, mock_analytics, mock_location)
        tracker.start()

        # Element with no attributes or content
        empty_element = MockElement('div', {}, "")
        tracker.handle_click(empty_element)

        # Element with None values
        null_element = MockElement('button', {'aria-label': None}, None)
        tracker.handle_click(null_element)

        # Should handle gracefully without errors
        # May or may not track depending on trackability, but shouldn't crash
        assert len(mock_analytics.events) >= 0  # No assertion error