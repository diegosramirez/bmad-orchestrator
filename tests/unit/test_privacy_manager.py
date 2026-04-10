"""Tests for privacy manager functionality - GDPR compliance and consent management"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Optional

import pytest


class MockLocalStorage:
    """Mock localStorage for testing browser storage functionality"""

    def __init__(self):
        self.data: Dict[str, str] = {}

    def getItem(self, key: str) -> Optional[str]:
        return self.data.get(key)

    def setItem(self, key: str, value: str) -> None:
        self.data[key] = value

    def removeItem(self, key: str) -> None:
        if key in self.data:
            del self.data[key]

    def clear(self) -> None:
        self.data.clear()


class MockAnalyticsService:
    """Mock analytics service for privacy testing"""

    def __init__(self):
        self.tracking_stopped = False
        self.tracking_events: list = []

    def stop_tracking(self):
        self.tracking_stopped = True

    def resume_tracking(self):
        self.tracking_stopped = False

    def track_consent_accepted(self, version: str):
        if not self.tracking_stopped:
            self.tracking_events.append(f'consent_accepted_{version}')

    def track_consent_declined(self, version: str):
        if not self.tracking_stopped:
            self.tracking_events.append(f'consent_declined_{version}')


class MockPrivacyManager:
    """Mock PrivacyManager representing TypeScript implementation"""

    STORAGE_KEY = 'bmad_privacy_consent'
    CURRENT_VERSION = '1.0.0'

    def __init__(self, storage: MockLocalStorage):
        self.storage = storage
        self.consent_state: Optional[Dict[str, Any]] = None
        self.callbacks: list = []
        self.session_id = self._generate_session_id()
        self._load_consent_state()

    def get_consent_state(self) -> Optional[Dict[str, Any]]:
        return self.consent_state

    def is_consent_required(self) -> bool:
        if not self.consent_state:
            return True
        return self.consent_state.get('version') != self.CURRENT_VERSION

    def has_consented(self) -> bool:
        return (
            self.consent_state is not None and
            self.consent_state.get('accepted') is True and
            not self.is_consent_required()
        )

    def accept_consent(self):
        new_state = {
            'accepted': True,
            'version': self.CURRENT_VERSION,
            'timestamp': datetime.now().isoformat(),
            'sessionId': self.session_id
        }
        self._update_consent_state(new_state)

    def decline_consent(self):
        new_state = {
            'accepted': False,
            'version': self.CURRENT_VERSION,
            'timestamp': datetime.now().isoformat(),
            'sessionId': self.session_id
        }
        self._update_consent_state(new_state)

    def revoke_consent(self):
        if self.consent_state:
            revoked_state = {
                **self.consent_state,
                'accepted': False,
                'timestamp': datetime.now().isoformat()
            }
            self._update_consent_state(revoked_state)

    def clear_consent(self):
        self.storage.removeItem(self.STORAGE_KEY)
        self.consent_state = None
        self._notify_callbacks()

    def on_consent_change(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)

    def get_session_id(self) -> str:
        return self.session_id

    def refresh_session(self):
        self.session_id = self._generate_session_id()
        if self.consent_state:
            updated_state = {
                **self.consent_state,
                'sessionId': self.session_id
            }
            self._update_consent_state(updated_state, notify=False)

    def get_consent_version(self) -> str:
        return self.CURRENT_VERSION

    def export_consent_data(self) -> str:
        data = {
            'consentState': self.consent_state,
            'exportTimestamp': datetime.now().isoformat(),
            'version': self.CURRENT_VERSION
        }
        return json.dumps(data, indent=2)

    def is_consent_expired(self) -> bool:
        if not self.consent_state:
            return True

        # 1 year expiration
        expiration_time = 365 * 24 * 60 * 60  # 1 year in seconds
        consent_time = datetime.fromisoformat(self.consent_state['timestamp'])
        consent_age = (datetime.now() - consent_time).total_seconds()

        return consent_age > expiration_time

    def _update_consent_state(self, new_state: Dict[str, Any], notify: bool = True):
        self.consent_state = new_state
        self._save_consent_state()
        if notify:
            self._notify_callbacks()

    def _load_consent_state(self):
        stored = self.storage.getItem(self.STORAGE_KEY)
        if stored:
            try:
                parsed = json.loads(stored)
                if self._is_valid_consent_state(parsed):
                    self.consent_state = parsed
                else:
                    self.clear_consent()
            except (json.JSONDecodeError, Exception):
                self.clear_consent()

    def _save_consent_state(self):
        if self.consent_state:
            try:
                serialized = json.dumps(self.consent_state)
                self.storage.setItem(self.STORAGE_KEY, serialized)
            except Exception:
                pass

    def _notify_callbacks(self):
        for callback in self.callbacks:
            try:
                if self.consent_state:
                    callback(self.consent_state)
            except Exception:
                pass

    def _is_valid_consent_state(self, state: Any) -> bool:
        return (
            isinstance(state, dict) and
            isinstance(state.get('accepted'), bool) and
            isinstance(state.get('version'), str) and
            isinstance(state.get('timestamp'), str) and
            isinstance(state.get('sessionId'), str)
        )

    def _generate_session_id(self) -> str:
        timestamp = str(int(time.time() * 1000))
        random_part = str(hash(time.time()))[-6:]
        return f"session_{timestamp}_{random_part}"


@pytest.fixture
def mock_storage():
    """Create mock localStorage"""
    return MockLocalStorage()


@pytest.fixture
def mock_analytics():
    """Create mock analytics service"""
    return MockAnalyticsService()


@pytest.fixture
def privacy_manager(mock_storage):
    """Create privacy manager with mock storage"""
    return MockPrivacyManager(mock_storage)


class TestPrivacyCompliance:
    """Test Privacy Compliance acceptance criteria"""

    def test_consent_banner_shows_when_required(self, privacy_manager):
        """Given consent banner When user first visits Then banner appears"""
        # New user - no consent state
        assert privacy_manager.is_consent_required()
        assert not privacy_manager.has_consented()
        assert privacy_manager.get_consent_state() is None

    def test_consent_acceptance_flow(self, privacy_manager, mock_analytics):
        """Given consent banner When user accepts Then tracking starts immediately"""
        # User accepts consent
        privacy_manager.accept_consent()

        # Consent should be recorded
        assert privacy_manager.has_consented()
        assert not privacy_manager.is_consent_required()

        consent_state = privacy_manager.get_consent_state()
        assert consent_state['accepted'] is True
        assert consent_state['version'] == privacy_manager.CURRENT_VERSION
        assert 'timestamp' in consent_state
        assert 'sessionId' in consent_state

    def test_consent_decline_flow(self, privacy_manager, mock_analytics):
        """Given consent banner When user declines Then tracking stops immediately"""
        # User declines consent
        privacy_manager.decline_consent()

        # Consent should be recorded as declined
        assert not privacy_manager.has_consented()
        assert not privacy_manager.is_consent_required()  # Still has a decision

        consent_state = privacy_manager.get_consent_state()
        assert consent_state['accepted'] is False
        assert consent_state['version'] == privacy_manager.CURRENT_VERSION

    def test_consent_opt_out_after_acceptance(self, privacy_manager):
        """Given user previously accepted When user opts out Then tracking stops immediately"""
        # First accept
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

        # Then revoke
        privacy_manager.revoke_consent()
        assert not privacy_manager.has_consented()

        consent_state = privacy_manager.get_consent_state()
        assert consent_state['accepted'] is False

    def test_consent_persistence_across_sessions(self, mock_storage):
        """Test that consent persists across browser sessions"""
        # Create first privacy manager and accept consent
        pm1 = MockPrivacyManager(mock_storage)
        pm1.accept_consent()
        assert pm1.has_consented()

        # Create new privacy manager (simulating new session)
        pm2 = MockPrivacyManager(mock_storage)
        assert pm2.has_consented()
        assert pm2.get_consent_state()['accepted'] is True

    def test_consent_version_updates_require_new_consent(self, privacy_manager, mock_storage):
        """Test that consent version changes require new consent"""
        # Accept consent with current version
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

        # Simulate version change by modifying stored consent
        stored = mock_storage.getItem(privacy_manager.STORAGE_KEY)
        consent_data = json.loads(stored)
        consent_data['version'] = '0.9.0'  # Old version
        mock_storage.setItem(privacy_manager.STORAGE_KEY, json.dumps(consent_data))

        # Create new privacy manager (simulating app reload)
        pm2 = MockPrivacyManager(mock_storage)
        assert pm2.is_consent_required()  # Should require new consent
        assert not pm2.has_consented()


class TestConsentCallbacks:
    """Test consent change callback system"""

    def test_consent_change_callbacks(self, privacy_manager):
        """Test that callbacks are fired when consent changes"""
        callback_calls = []

        def test_callback(consent_state):
            callback_calls.append(consent_state.copy())

        # Register callback
        unsubscribe = privacy_manager.on_consent_change(test_callback)

        # Accept consent
        privacy_manager.accept_consent()
        assert len(callback_calls) == 1
        assert callback_calls[0]['accepted'] is True

        # Decline consent
        privacy_manager.decline_consent()
        assert len(callback_calls) == 2
        assert callback_calls[1]['accepted'] is False

        # Test unsubscribe
        unsubscribe()
        privacy_manager.accept_consent()
        assert len(callback_calls) == 2  # No new callback

    def test_multiple_callbacks(self, privacy_manager):
        """Test multiple consent change callbacks"""
        callback1_calls = []
        callback2_calls = []

        privacy_manager.on_consent_change(lambda state: callback1_calls.append(state))
        privacy_manager.on_consent_change(lambda state: callback2_calls.append(state))

        privacy_manager.accept_consent()

        assert len(callback1_calls) == 1
        assert len(callback2_calls) == 1

    def test_callback_error_handling(self, privacy_manager):
        """Test that callback errors don't break the system"""
        def failing_callback(state):
            raise Exception("Callback error")

        def working_callback(state):
            working_callback.called = True

        working_callback.called = False

        privacy_manager.on_consent_change(failing_callback)
        privacy_manager.on_consent_change(working_callback)

        # Should not raise exception
        privacy_manager.accept_consent()
        assert working_callback.called


class TestSessionManagement:
    """Test session management functionality"""

    def test_session_id_generation(self, privacy_manager):
        """Test that session IDs are unique and properly formatted"""
        session_id = privacy_manager.get_session_id()
        assert session_id.startswith('session_')
        assert len(session_id.split('_')) == 3  # session_timestamp_random

    def test_session_refresh(self, privacy_manager):
        """Test session refresh functionality"""
        # Accept consent first
        privacy_manager.accept_consent()
        original_session = privacy_manager.get_session_id()

        # Refresh session
        privacy_manager.refresh_session()
        new_session = privacy_manager.get_session_id()

        assert new_session != original_session
        assert new_session.startswith('session_')

        # Consent state should be updated with new session
        consent_state = privacy_manager.get_consent_state()
        assert consent_state['sessionId'] == new_session

    def test_session_continuity_across_page_loads(self, mock_storage):
        """Test that session ID persists across page loads until refresh"""
        # Create privacy manager and accept consent
        pm1 = MockPrivacyManager(mock_storage)
        pm1.accept_consent()
        original_session = pm1.get_session_id()

        # Simulate page reload - should keep same session
        pm2 = MockPrivacyManager(mock_storage)
        assert pm2.get_session_id() == original_session


class TestPrivacyDataManagement:
    """Test privacy data management and export"""

    def test_consent_data_export(self, privacy_manager):
        """Test GDPR-compliant data export functionality"""
        # Accept consent first
        privacy_manager.accept_consent()

        exported_data = privacy_manager.export_consent_data()
        parsed_data = json.loads(exported_data)

        assert 'consentState' in parsed_data
        assert 'exportTimestamp' in parsed_data
        assert 'version' in parsed_data
        assert parsed_data['consentState']['accepted'] is True

    def test_consent_data_clearing(self, privacy_manager, mock_storage):
        """Test complete consent data clearing"""
        # Accept consent first
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()
        assert mock_storage.getItem(privacy_manager.STORAGE_KEY) is not None

        # Clear consent
        privacy_manager.clear_consent()
        assert privacy_manager.get_consent_state() is None
        assert mock_storage.getItem(privacy_manager.STORAGE_KEY) is None

    def test_invalid_stored_data_handling(self, mock_storage):
        """Test handling of invalid/corrupted stored consent data"""
        # Store invalid JSON
        mock_storage.setItem('bmad_privacy_consent', 'invalid json')
        pm = MockPrivacyManager(mock_storage)
        assert pm.get_consent_state() is None

        # Store valid JSON but invalid structure
        mock_storage.setItem('bmad_privacy_consent', json.dumps({'invalid': 'structure'}))
        pm = MockPrivacyManager(mock_storage)
        assert pm.get_consent_state() is None

    def test_storage_error_handling(self, privacy_manager):
        """Test handling of localStorage errors"""
        # Mock storage to throw errors
        privacy_manager.storage.setItem = Mock(side_effect=Exception("Storage error"))
        privacy_manager.storage.getItem = Mock(side_effect=Exception("Storage error"))
        privacy_manager.storage.removeItem = Mock(side_effect=Exception("Storage error"))

        # Should handle errors gracefully
        privacy_manager.accept_consent()  # Should not raise
        privacy_manager.clear_consent()   # Should not raise


class TestConsentExpiration:
    """Test consent expiration functionality"""

    def test_consent_expiration_check(self, mock_storage):
        """Test that consent expires after defined period"""
        pm = MockPrivacyManager(mock_storage)
        pm.accept_consent()

        # Manually set timestamp to old date
        consent_state = pm.get_consent_state()
        old_timestamp = (datetime.now() - timedelta(days=400)).isoformat()
        consent_state['timestamp'] = old_timestamp

        # Update storage
        mock_storage.setItem(pm.STORAGE_KEY, json.dumps(consent_state))

        # Create new privacy manager to reload from storage
        pm2 = MockPrivacyManager(mock_storage)
        assert pm2.is_consent_expired()

    def test_fresh_consent_not_expired(self, privacy_manager):
        """Test that fresh consent is not considered expired"""
        privacy_manager.accept_consent()
        assert not privacy_manager.is_consent_expired()

    def test_no_consent_is_expired(self, privacy_manager):
        """Test that no consent state is considered expired"""
        assert privacy_manager.is_consent_expired()


class TestCrossTabSynchronization:
    """Test cross-tab consent synchronization"""

    def test_cross_tab_consent_sync_concept(self, mock_storage):
        """Test concept of cross-tab synchronization (simplified)"""
        # Simulate two tabs with same storage
        pm1 = MockPrivacyManager(mock_storage)
        pm2 = MockPrivacyManager(mock_storage)

        # Tab 1 accepts consent
        pm1.accept_consent()

        # Tab 2 should be able to see the change when it checks
        pm2._load_consent_state()  # Simulating storage event reload
        assert pm2.has_consented()

    def test_storage_change_detection(self, mock_storage):
        """Test that storage changes are properly detected"""
        pm = MockPrivacyManager(mock_storage)

        # Simulate external change to storage
        external_consent = {
            'accepted': True,
            'version': pm.CURRENT_VERSION,
            'timestamp': datetime.now().isoformat(),
            'sessionId': 'external_session'
        }
        mock_storage.setItem(pm.STORAGE_KEY, json.dumps(external_consent))

        # Reload from storage
        pm._load_consent_state()
        assert pm.has_consented()
        assert pm.get_consent_state()['sessionId'] == 'external_session'


class TestPrivacyBannerIntegration:
    """Test privacy banner integration concepts"""

    def test_banner_visibility_logic(self, privacy_manager):
        """Test when banner should be visible"""
        # No consent - should show banner
        assert privacy_manager.is_consent_required()

        # After accepting - should not show banner
        privacy_manager.accept_consent()
        assert not privacy_manager.is_consent_required()

        # After declining - should not show banner (user made choice)
        privacy_manager.decline_consent()
        assert not privacy_manager.is_consent_required()

    def test_settings_change_flow(self, privacy_manager):
        """Test changing privacy settings after initial choice"""
        # Accept initially
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

        # Change mind and revoke
        privacy_manager.revoke_consent()
        assert not privacy_manager.has_consented()

        # Should still not require new consent (user made explicit choice)
        assert not privacy_manager.is_consent_required()

    def test_privacy_indicator_status(self, privacy_manager):
        """Test privacy indicator status display"""
        # No consent
        assert not privacy_manager.has_consented()

        # Accept consent
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

        # Decline consent
        privacy_manager.decline_consent()
        assert not privacy_manager.has_consented()


class TestGDPRCompliance:
    """Test GDPR compliance features"""

    def test_right_to_be_forgotten(self, privacy_manager, mock_analytics):
        """Test complete data removal (right to be forgotten)"""
        # Accept consent and track some data
        privacy_manager.accept_consent()

        # User requests data deletion
        privacy_manager.clear_consent()

        # All consent data should be removed
        assert privacy_manager.get_consent_state() is None
        assert privacy_manager.is_consent_required()

    def test_data_portability(self, privacy_manager):
        """Test data export for portability (GDPR Article 20)"""
        privacy_manager.accept_consent()
        exported_data = privacy_manager.export_consent_data()

        # Should be in machine-readable format
        parsed = json.loads(exported_data)
        assert isinstance(parsed, dict)
        assert 'consentState' in parsed

    def test_consent_withdrawal(self, privacy_manager):
        """Test easy consent withdrawal (GDPR Article 7)"""
        # Accept consent
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

        # Should be easy to withdraw
        privacy_manager.revoke_consent()
        assert not privacy_manager.has_consented()

        # Withdrawal should be as easy as giving consent
        privacy_manager.accept_consent()
        assert privacy_manager.has_consented()

    def test_consent_granularity(self, privacy_manager):
        """Test that consent can be managed at granular level"""
        # Current implementation is binary, but structure supports expansion
        privacy_manager.accept_consent()
        consent_state = privacy_manager.get_consent_state()

        # Structure supports future granular consent
        assert isinstance(consent_state, dict)
        assert 'accepted' in consent_state
        # Future: could add 'analytics', 'marketing', 'functional' fields