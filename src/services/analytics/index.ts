// Main analytics service exports
export {
  analytics,
  type AnalyticsConfig,
  type EventProperties,
  type PageViewProperties,
  type ElementClickProperties,
  type SessionProperties
} from './AnalyticsService';

// Privacy management exports
export {
  privacyManager,
  type ConsentState,
  type PrivacyPreferences,
  type ConsentChangeCallback
} from './PrivacyManager';

// Event collection exports
export {
  usePageViewTracking,
  initializeEventCollectors,
  cleanupEventCollectors,
  clickTracker,
  SessionTracker,
  type PageViewData,
  type ClickEventData
} from './EventCollectors';

// Environment configuration helper
export interface PostHogEnvironmentConfig {
  apiKey: string;
  host?: string;
  disabled?: boolean;
}

export const getAnalyticsConfig = (): PostHogEnvironmentConfig => {
  const isDevelopment = process.env.NODE_ENV === 'development';
  const isTest = process.env.NODE_ENV === 'test';

  // Environment-specific configuration
  return {
    apiKey: process.env.REACT_APP_POSTHOG_API_KEY || process.env.VITE_POSTHOG_API_KEY || '',
    host: process.env.REACT_APP_POSTHOG_HOST || process.env.VITE_POSTHOG_HOST || 'https://app.posthog.com',
    disabled: isTest || isDevelopment || (!process.env.REACT_APP_POSTHOG_API_KEY && !process.env.VITE_POSTHOG_API_KEY)
  };
};

// Analytics initialization helper
export const initializeAnalytics = async (customConfig?: Partial<PostHogEnvironmentConfig>): Promise<void> => {
  const config = {
    ...getAnalyticsConfig(),
    ...customConfig
  };

  if (!config.apiKey && !config.disabled) {
    console.warn('[Analytics] No PostHog API key provided. Analytics will be disabled.');
    config.disabled = true;
  }

  try {
    await analytics.initialize(config);

    // Initialize event collectors only after analytics is ready
    if (!config.disabled) {
      initializeEventCollectors();
    }

    console.log('[Analytics] Successfully initialized', {
      environment: process.env.NODE_ENV,
      disabled: config.disabled
    });
  } catch (error) {
    console.error('[Analytics] Failed to initialize:', error);
  }
};

// Utility functions for common tracking scenarios
export const trackFeatureUsage = (featureName: string, metadata?: Record<string, any>) => {
  analytics.track('feature_used', {
    feature_name: featureName,
    timestamp: new Date(),
    ...metadata
  });
};

export const trackUserJourney = (step: string, journeyName: string, metadata?: Record<string, any>) => {
  analytics.track('user_journey_step', {
    step,
    journey_name: journeyName,
    timestamp: new Date(),
    ...metadata
  });
};

export const trackPerformanceMetric = (metricName: string, value: number, unit: string = 'ms') => {
  analytics.track('performance_metric', {
    metric_name: metricName,
    value,
    unit,
    timestamp: new Date()
  });
};

export const trackError = (error: Error, context?: string) => {
  analytics.track('client_error', {
    error_message: error.message,
    error_stack: error.stack,
    error_name: error.name,
    context: context || 'unknown',
    timestamp: new Date()
  });
};

// Privacy utilities
export const checkConsentStatus = () => {
  return {
    hasConsented: privacyManager.hasConsented(),
    consentRequired: privacyManager.isConsentRequired(),
    consentState: privacyManager.getConsentState()
  };
};

export const exportUserData = () => {
  return privacyManager.exportConsentData();
};

// Analytics health check
export const getAnalyticsHealth = () => {
  return {
    isReady: analytics.isReady(),
    config: analytics.getConfig(),
    consent: checkConsentStatus(),
    environment: process.env.NODE_ENV
  };
};