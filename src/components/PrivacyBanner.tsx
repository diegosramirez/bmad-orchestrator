import React, { useState, useEffect } from 'react';
import { privacyManager, ConsentState } from '../services/analytics/PrivacyManager';
import { analytics } from '../services/analytics/AnalyticsService';

interface PrivacyBannerProps {
  onConsentChange?: (consented: boolean) => void;
  showSettingsLink?: boolean;
  customMessage?: string;
  position?: 'top' | 'bottom';
  theme?: 'light' | 'dark';
}

export const PrivacyBanner: React.FC<PrivacyBannerProps> = ({
  onConsentChange,
  showSettingsLink = true,
  customMessage,
  position = 'bottom',
  theme = 'light'
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [consentState, setConsentState] = useState<ConsentState | null>(null);

  useEffect(() => {
    // Check if consent is required
    const shouldShowBanner = privacyManager.isConsentRequired();
    setIsVisible(shouldShowBanner);
    setConsentState(privacyManager.getConsentState());

    // Listen for consent changes
    const unsubscribe = privacyManager.onConsentChange((newState) => {
      setConsentState(newState);
      setIsVisible(privacyManager.isConsentRequired());
      onConsentChange?.(newState.accepted);
    });

    // Setup cross-tab sync
    const cleanupSync = privacyManager.syncAcrossTabs();

    return () => {
      unsubscribe();
      cleanupSync();
    };
  }, [onConsentChange]);

  const handleAccept = async () => {
    setIsLoading(true);

    try {
      privacyManager.acceptConsent();
      analytics.trackConsentAccepted(privacyManager.getConsentVersion());

      // Short delay for user feedback
      setTimeout(() => {
        setIsLoading(false);
        setIsVisible(false);
      }, 300);
    } catch (error) {
      console.error('[PrivacyBanner] Error accepting consent:', error);
      setIsLoading(false);
    }
  };

  const handleDecline = async () => {
    setIsLoading(true);

    try {
      privacyManager.declineConsent();
      analytics.trackConsentDeclined(privacyManager.getConsentVersion());

      // Short delay for user feedback
      setTimeout(() => {
        setIsLoading(false);
        setIsVisible(false);
      }, 300);
    } catch (error) {
      console.error('[PrivacyBanner] Error declining consent:', error);
      setIsLoading(false);
    }
  };

  const handleSettingsClick = () => {
    // Emit custom event for settings modal or navigate to privacy page
    const event = new CustomEvent('privacy-settings-requested');
    window.dispatchEvent(event);
  };

  if (!isVisible) {
    return null;
  }

  const defaultMessage = customMessage ||
    "We use analytics to improve your experience. Your privacy matters to us - you can opt out anytime.";

  const bannerClasses = [
    'privacy-banner',
    `privacy-banner--${position}`,
    `privacy-banner--${theme}`,
    isLoading ? 'privacy-banner--loading' : ''
  ].filter(Boolean).join(' ');

  const acceptButtonClasses = [
    'privacy-banner__button',
    'privacy-banner__button--accept',
    isLoading ? 'privacy-banner__button--loading' : ''
  ].filter(Boolean).join(' ');

  const declineButtonClasses = [
    'privacy-banner__button',
    'privacy-banner__button--decline',
    isLoading ? 'privacy-banner__button--loading' : ''
  ].filter(Boolean).join(' ');

  return (
    <>
      <div className={bannerClasses} role="dialog" aria-live="polite" aria-label="Privacy consent banner">
        <div className="privacy-banner__content">
          <div className="privacy-banner__message">
            <p>{defaultMessage}</p>
          </div>

          <div className="privacy-banner__actions">
            <button
              className={acceptButtonClasses}
              onClick={handleAccept}
              disabled={isLoading}
              aria-label="Accept analytics cookies"
            >
              {isLoading ? 'Processing...' : 'Accept'}
            </button>

            <button
              className={declineButtonClasses}
              onClick={handleDecline}
              disabled={isLoading}
              aria-label="Decline analytics cookies"
            >
              {isLoading ? 'Processing...' : 'Decline'}
            </button>

            {showSettingsLink && (
              <button
                className="privacy-banner__link"
                onClick={handleSettingsClick}
                disabled={isLoading}
                aria-label="Privacy settings"
              >
                Settings
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Accessible backdrop */}
      <div className="privacy-banner__backdrop" />

      {/* Inline styles for the component */}
      <style jsx>{`
        .privacy-banner {
          position: fixed;
          left: 0;
          right: 0;
          z-index: 9999;
          max-width: 100%;
          padding: 16px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          font-size: 14px;
          line-height: 1.4;
          transition: transform 0.3s ease-in-out, opacity 0.3s ease-in-out;
        }

        .privacy-banner--top {
          top: 0;
          border-bottom: 1px solid #e0e0e0;
        }

        .privacy-banner--bottom {
          bottom: 0;
          border-top: 1px solid #e0e0e0;
        }

        .privacy-banner--light {
          background: #ffffff;
          color: #333333;
          box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
        }

        .privacy-banner--dark {
          background: #2d2d2d;
          color: #ffffff;
          box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.3);
        }

        .privacy-banner__content {
          max-width: 1200px;
          margin: 0 auto;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          flex-wrap: wrap;
        }

        .privacy-banner__message {
          flex: 1;
          min-width: 200px;
        }

        .privacy-banner__message p {
          margin: 0;
        }

        .privacy-banner__actions {
          display: flex;
          align-items: center;
          gap: 12px;
          flex-wrap: wrap;
        }

        .privacy-banner__button {
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease-in-out;
          white-space: nowrap;
          min-width: 80px;
        }

        .privacy-banner__button:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .privacy-banner__button--accept {
          background: #007bff;
          color: white;
        }

        .privacy-banner__button--accept:hover:not(:disabled) {
          background: #0056b3;
        }

        .privacy-banner__button--decline {
          background: transparent;
          color: #666666;
          border: 1px solid #d0d0d0;
        }

        .privacy-banner--dark .privacy-banner__button--decline {
          color: #cccccc;
          border-color: #555555;
        }

        .privacy-banner__button--decline:hover:not(:disabled) {
          background: #f8f9fa;
          border-color: #999999;
        }

        .privacy-banner--dark .privacy-banner__button--decline:hover:not(:disabled) {
          background: #3d3d3d;
          border-color: #777777;
        }

        .privacy-banner__button--loading {
          position: relative;
        }

        .privacy-banner__button--loading::after {
          content: '';
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 16px;
          height: 16px;
          border: 2px solid transparent;
          border-top: 2px solid currentColor;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        .privacy-banner__link {
          background: none;
          border: none;
          color: #007bff;
          text-decoration: underline;
          cursor: pointer;
          font-size: 14px;
          padding: 4px 8px;
        }

        .privacy-banner--dark .privacy-banner__link {
          color: #66b3ff;
        }

        .privacy-banner__link:hover:not(:disabled) {
          color: #0056b3;
        }

        .privacy-banner--dark .privacy-banner__link:hover:not(:disabled) {
          color: #99ccff;
        }

        .privacy-banner__backdrop {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.1);
          z-index: 9998;
          pointer-events: none;
        }

        @keyframes spin {
          0% { transform: translate(-50%, -50%) rotate(0deg); }
          100% { transform: translate(-50%, -50%) rotate(360deg); }
        }

        @media (max-width: 768px) {
          .privacy-banner__content {
            flex-direction: column;
            text-align: center;
          }

          .privacy-banner__actions {
            justify-content: center;
            width: 100%;
          }

          .privacy-banner__button {
            flex: 1;
            min-width: 120px;
          }
        }

        @media (max-width: 480px) {
          .privacy-banner {
            padding: 12px;
          }

          .privacy-banner__actions {
            flex-direction: column;
            gap: 8px;
          }

          .privacy-banner__button {
            width: 100%;
          }
        }
      `}</style>
    </>
  );
};

// Privacy indicator component for showing current consent status
interface PrivacyIndicatorProps {
  showStatus?: boolean;
  onManageClick?: () => void;
}

export const PrivacyIndicator: React.FC<PrivacyIndicatorProps> = ({
  showStatus = true,
  onManageClick
}) => {
  const [consentState, setConsentState] = useState<ConsentState | null>(null);

  useEffect(() => {
    setConsentState(privacyManager.getConsentState());

    const unsubscribe = privacyManager.onConsentChange((newState) => {
      setConsentState(newState);
    });

    return unsubscribe;
  }, []);

  const handleManageClick = () => {
    onManageClick?.();

    // Also emit the settings event
    const event = new CustomEvent('privacy-settings-requested');
    window.dispatchEvent(event);
  };

  if (!showStatus || !consentState) {
    return null;
  }

  const statusText = consentState.accepted ? 'Analytics enabled' : 'Analytics disabled';
  const statusColor = consentState.accepted ? '#28a745' : '#6c757d';

  return (
    <div className="privacy-indicator">
      <span className="privacy-indicator__status" style={{ color: statusColor }}>
        {statusText}
      </span>
      <button
        className="privacy-indicator__manage"
        onClick={handleManageClick}
        aria-label="Manage privacy preferences"
      >
        Manage
      </button>

      <style jsx>{`
        .privacy-indicator {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: #666;
        }

        .privacy-indicator__status {
          font-weight: 500;
        }

        .privacy-indicator__manage {
          background: none;
          border: none;
          color: #007bff;
          text-decoration: underline;
          cursor: pointer;
          font-size: 12px;
          padding: 0;
        }

        .privacy-indicator__manage:hover {
          color: #0056b3;
        }
      `}</style>
    </div>
  );
};