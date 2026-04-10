import { useEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';
import { analytics } from './AnalyticsService';
import { privacyManager } from './PrivacyManager';

export interface PageViewData {
  route: string;
  referrer: string;
  timestamp: Date;
  user_id?: string;
  [key: string]: string | number | boolean | Date | undefined;
}

export interface ClickEventData {
  element_type: string;
  element_label: string;
  page_context: string;
  [key: string]: string | number | boolean | Date | undefined;
}

// Custom hook for automatic page view tracking
export function usePageViewTracking(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const lastTrackedPath = useRef<string>('');

  useEffect(() => {
    // Only track if consent has been given
    if (!privacyManager.hasConsented()) {
      return;
    }

    const currentPath = location.pathname + location.search;

    // Avoid duplicate tracking for the same path
    if (lastTrackedPath.current === currentPath) {
      return;
    }

    lastTrackedPath.current = currentPath;

    // Track page view with required properties
    const pageViewData: PageViewData = {
      route: currentPath,
      referrer: document.referrer || 'direct',
      timestamp: new Date(),
      user_id: getCurrentUserId() // Optional, implement based on your auth system
    };

    analytics.trackPageView(pageViewData);

    // Track navigation method for additional insights
    if (navigationType) {
      analytics.track('navigation_method', {
        method: navigationType,
        from: lastTrackedPath.current || 'unknown',
        to: currentPath,
        timestamp: new Date()
      });
    }

  }, [location, navigationType]);
}

// Event delegation system for click tracking
export class ClickTracker {
  private static instance: ClickTracker;
  private isActive = false;
  private boundHandler: ((event: Event) => void) | null = null;

  private constructor() {
    // Private constructor for singleton
  }

  public static getInstance(): ClickTracker {
    if (!ClickTracker.instance) {
      ClickTracker.instance = new ClickTracker();
    }
    return ClickTracker.instance;
  }

  public start(): void {
    if (this.isActive) {
      return;
    }

    this.boundHandler = this.handleClick.bind(this);
    document.addEventListener('click', this.boundHandler, true);
    this.isActive = true;
  }

  public stop(): void {
    if (!this.isActive || !this.boundHandler) {
      return;
    }

    document.removeEventListener('click', this.boundHandler, true);
    this.boundHandler = null;
    this.isActive = false;
  }

  private handleClick(event: Event): void {
    // Only track if consent has been given
    if (!privacyManager.hasConsented()) {
      return;
    }

    const target = event.target as HTMLElement;
    if (!target) {
      return;
    }

    const clickData = this.extractClickData(target);
    if (clickData) {
      analytics.trackElementClick(clickData);
    }
  }

  private extractClickData(element: HTMLElement): ClickEventData | null {
    // Filter non-interactive elements
    if (!this.isTrackableElement(element)) {
      return null;
    }

    const elementType = this.getElementType(element);
    const elementLabel = this.getElementLabel(element);
    const pageContext = this.getPageContext();

    return {
      element_type: elementType,
      element_label: elementLabel,
      page_context: pageContext
    };
  }

  private isTrackableElement(element: HTMLElement): boolean {
    const trackableTypes = [
      'button',
      'a',
      'input',
      'select',
      'textarea',
      'form'
    ];

    const tagName = element.tagName.toLowerCase();

    // Check if it's a trackable element type
    if (trackableTypes.includes(tagName)) {
      return true;
    }

    // Check if element has click handler or role
    if (element.onclick ||
        element.getAttribute('role') === 'button' ||
        element.hasAttribute('data-track')) {
      return true;
    }

    // Check if parent is trackable (for nested elements)
    const parent = element.closest('button, a, [role="button"], [data-track]');
    return !!parent;
  }

  private getElementType(element: HTMLElement): string {
    const tagName = element.tagName.toLowerCase();

    // Handle specific input types
    if (tagName === 'input') {
      const type = element.getAttribute('type') || 'text';
      return `input_${type}`;
    }

    // Handle elements with roles
    const role = element.getAttribute('role');
    if (role) {
      return `${tagName}_${role}`;
    }

    // Handle form submission
    if (tagName === 'form') {
      return 'form_submission';
    }

    // Handle custom trackable elements
    if (element.hasAttribute('data-track-type')) {
      return element.getAttribute('data-track-type') || tagName;
    }

    return tagName;
  }

  private getElementLabel(element: HTMLElement): string {
    // Priority order for extracting element label
    const labelSources = [
      () => element.getAttribute('data-track-label'),
      () => element.getAttribute('aria-label'),
      () => element.getAttribute('title'),
      () => element.getAttribute('placeholder'),
      () => element.getAttribute('value'),
      () => element.textContent?.trim(),
      () => element.getAttribute('name'),
      () => element.getAttribute('id'),
      () => element.className.split(' ').find(cls => cls.includes('btn') || cls.includes('button'))
    ];

    for (const getLabel of labelSources) {
      const label = getLabel();
      if (label && label.length > 0) {
        return label.substring(0, 100); // Limit label length
      }
    }

    return 'unlabeled_element';
  }

  private getPageContext(): string {
    // Extract current page context
    const path = window.location.pathname;
    const sections = path.split('/').filter(Boolean);

    if (sections.length === 0) {
      return 'home';
    }

    // Return the main section or first part of the path
    return sections[0] || 'unknown';
  }
}

// Session tracking utilities
export class SessionTracker {
  private static sessionStarted = false;
  private static sessionId: string = '';

  public static startSession(): void {
    if (this.sessionStarted) {
      return;
    }

    if (!privacyManager.hasConsented()) {
      return;
    }

    this.sessionId = privacyManager.getSessionId();
    this.sessionStarted = true;

    const sessionData = {
      device_type: this.getDeviceType(),
      browser: this.getBrowserInfo(),
      entry_point: this.getEntryPoint()
    };

    analytics.trackSessionStart(sessionData);

    // Track session duration on page unload
    window.addEventListener('beforeunload', this.endSession.bind(this));
  }

  public static endSession(): void {
    if (!this.sessionStarted || !privacyManager.hasConsented()) {
      return;
    }

    analytics.track('session_end', {
      session_id: this.sessionId,
      timestamp: new Date()
    });
  }

  private static getDeviceType(): string {
    const userAgent = navigator.userAgent;

    if (/tablet|ipad|playbook|silk/i.test(userAgent)) {
      return 'tablet';
    }

    if (/mobile|iphone|ipod|android|blackberry|opera|mini|windows\sce|palm|smartphone|iemobile/i.test(userAgent)) {
      return 'mobile';
    }

    return 'desktop';
  }

  private static getBrowserInfo(): string {
    const userAgent = navigator.userAgent;

    if (userAgent.includes('Chrome')) return 'chrome';
    if (userAgent.includes('Firefox')) return 'firefox';
    if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) return 'safari';
    if (userAgent.includes('Edge')) return 'edge';
    if (userAgent.includes('Opera')) return 'opera';

    return 'unknown';
  }

  private static getEntryPoint(): string {
    const referrer = document.referrer;

    if (!referrer) {
      return 'direct';
    }

    try {
      const referrerDomain = new URL(referrer).hostname;
      const currentDomain = window.location.hostname;

      if (referrerDomain === currentDomain) {
        return 'internal';
      }

      // Check for common search engines and social media
      if (referrerDomain.includes('google')) return 'google';
      if (referrerDomain.includes('facebook')) return 'facebook';
      if (referrerDomain.includes('twitter')) return 'twitter';
      if (referrerDomain.includes('linkedin')) return 'linkedin';

      return 'external';
    } catch {
      return 'unknown';
    }
  }
}

// Utility function to get current user ID (implement based on your auth system)
function getCurrentUserId(): string | undefined {
  // This should be implemented based on your authentication system
  // For example, you might get this from a context, localStorage, or cookie
  try {
    const user = localStorage.getItem('user');
    if (user) {
      const userData = JSON.parse(user);
      return userData.id || userData.email;
    }
  } catch {
    // Ignore parsing errors
  }

  return undefined;
}

// Initialize tracking systems
export function initializeEventCollectors(): void {
  // Start click tracking
  const clickTracker = ClickTracker.getInstance();
  clickTracker.start();

  // Start session tracking
  SessionTracker.startSession();

  // Listen for consent changes
  privacyManager.onConsentChange((consentState) => {
    if (consentState.accepted) {
      // Resume tracking
      clickTracker.start();
      analytics.resumeTracking();
    } else {
      // Stop tracking
      clickTracker.stop();
      analytics.stopTracking();
    }
  });
}

// Cleanup function for when the app unmounts
export function cleanupEventCollectors(): void {
  const clickTracker = ClickTracker.getInstance();
  clickTracker.stop();
}

// Export the click tracker instance for manual control if needed
export const clickTracker = ClickTracker.getInstance();