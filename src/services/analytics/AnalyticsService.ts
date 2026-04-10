import posthog, { PostHog } from 'posthog-js';

export interface AnalyticsConfig {
  apiKey: string;
  host?: string;
  disabled?: boolean;
}

export interface EventProperties {
  [key: string]: string | number | boolean | Date | undefined;
}

export interface PageViewProperties extends EventProperties {
  route: string;
  referrer: string;
  timestamp: Date;
  user_id?: string;
}

export interface ElementClickProperties extends EventProperties {
  element_type: string;
  element_label: string;
  page_context: string;
}

export interface SessionProperties extends EventProperties {
  device_type: string;
  browser: string;
  entry_point: string;
}

class AnalyticsService {
  private static instance: AnalyticsService;
  private posthog: PostHog | null = null;
  private initialized = false;
  private config: AnalyticsConfig | null = null;
  private eventQueue: Array<{ event: string; properties: EventProperties }> = [];
  private retryCount = 0;
  private maxRetries = 3;
  private retryTimeoutId: number | null = null;

  private constructor() {
    // Private constructor for singleton
  }

  public static getInstance(): AnalyticsService {
    if (!AnalyticsService.instance) {
      AnalyticsService.instance = new AnalyticsService();
    }
    return AnalyticsService.instance;
  }

  public async initialize(config: AnalyticsConfig): Promise<void> {
    if (this.initialized) {
      return;
    }

    this.config = config;

    // Environment validation
    const isProduction = process.env.NODE_ENV === 'production';
    const isDevelopment = process.env.NODE_ENV === 'development';

    // Prevent test data pollution in development
    if (isDevelopment && !config.disabled) {
      console.warn('[Analytics] Running in development mode - events will be tagged accordingly');
    }

    if (config.disabled) {
      console.log('[Analytics] Analytics disabled via configuration');
      this.initialized = true;
      return;
    }

    try {
      const startTime = performance.now();

      // Lazy load PostHog with performance monitoring
      posthog.init(config.apiKey, {
        api_host: config.host || 'https://app.posthog.com',
        loaded: (posthog) => {
          this.posthog = posthog;
          this.initialized = true;

          const loadTime = performance.now() - startTime;
          if (loadTime > 50) {
            console.warn(`[Analytics] PostHog initialization took ${loadTime.toFixed(2)}ms (exceeds 50ms threshold)`);
          }

          // Process queued events
          this.processEventQueue();
        },
        capture_pageview: false, // We'll handle page views manually
        disable_session_recording: !isProduction, // Only enable in production
        persistence: 'localStorage',
        property_denylist: isDevelopment ? [] : ['$current_url', '$pathname'],
        sanitize_properties: (properties) => {
          // Add environment tag to all events
          return {
            ...properties,
            environment: isDevelopment ? 'development' : 'production'
          };
        }
      });

    } catch (error) {
      console.error('[Analytics] Failed to initialize PostHog:', error);
      this.initialized = true; // Mark as initialized to prevent retries
    }
  }

  public trackPageView(properties: PageViewProperties): void {
    this.track('page_view', properties);
  }

  public trackElementClick(properties: ElementClickProperties): void {
    this.track('element_click', properties);
  }

  public trackSessionStart(properties: SessionProperties): void {
    this.track('session_start', properties);
  }

  public trackUserIdentified(userId: string, sessionId: string): void {
    this.track('user_identified', { user_id: userId, session_id: sessionId });
    this.identify(userId);
  }

  public trackConsentAccepted(version: string): void {
    this.track('privacy_consent_accepted', { consent_version: version, timestamp: new Date() });
  }

  public trackConsentDeclined(version: string): void {
    this.track('privacy_consent_declined', { consent_version: version, timestamp: new Date() });
  }

  public track(event: string, properties: EventProperties): void {
    if (!this.initialized || this.config?.disabled) {
      // Queue events until initialized or if disabled
      if (!this.config?.disabled) {
        this.eventQueue.push({ event, properties });
      }
      return;
    }

    if (!this.posthog) {
      console.warn('[Analytics] PostHog not available, queueing event:', event);
      this.eventQueue.push({ event, properties });
      return;
    }

    try {
      // Add timestamp if not present
      const eventProperties = {
        ...properties,
        timestamp: properties.timestamp || new Date()
      };

      this.posthog.capture(event, eventProperties);
      this.retryCount = 0; // Reset retry count on success
      this.clearRetryTimeout(); // Clear any pending retry timeout
    } catch (error) {
      console.error('[Analytics] Failed to track event:', event, error);
      this.handleTrackingError(event, properties);
    }
  }

  public identify(userId: string, properties?: EventProperties): void {
    if (!this.initialized || this.config?.disabled || !this.posthog) {
      return;
    }

    try {
      this.posthog.identify(userId, properties);
    } catch (error) {
      console.error('[Analytics] Failed to identify user:', error);
    }
  }

  public reset(): void {
    if (!this.initialized || this.config?.disabled || !this.posthog) {
      return;
    }

    try {
      this.posthog.reset();
      this.eventQueue = []; // Clear event queue
      this.clearRetryTimeout(); // Clear any pending retry timeout
    } catch (error) {
      console.error('[Analytics] Failed to reset analytics:', error);
    }
  }

  public stopTracking(): void {
    if (!this.initialized || this.config?.disabled) {
      return;
    }

    try {
      // Clear event queue immediately
      this.eventQueue = [];
      this.clearRetryTimeout(); // Clear any pending retry timeout

      if (this.posthog) {
        this.posthog.opt_out_capturing();
      }
    } catch (error) {
      console.error('[Analytics] Failed to stop tracking:', error);
    }
  }

  public resumeTracking(): void {
    if (!this.initialized || this.config?.disabled || !this.posthog) {
      return;
    }

    try {
      this.posthog.opt_in_capturing();
    } catch (error) {
      console.error('[Analytics] Failed to resume tracking:', error);
    }
  }

  private processEventQueue(): void {
    if (this.eventQueue.length === 0) {
      return;
    }

    const queuedEvents = [...this.eventQueue];
    this.eventQueue = [];

    queuedEvents.forEach(({ event, properties }) => {
      this.track(event, properties);
    });
  }

  private handleTrackingError(event: string, properties: EventProperties): void {
    if (this.retryCount >= this.maxRetries) {
      console.error(`[Analytics] Max retries exceeded for event: ${event}`);
      return;
    }

    // Exponential backoff retry
    const retryDelay = Math.pow(2, this.retryCount) * 1000;
    this.retryCount++;

    this.retryTimeoutId = window.setTimeout(() => {
      console.log(`[Analytics] Retrying event: ${event} (attempt ${this.retryCount})`);
      this.retryTimeoutId = null;
      this.track(event, properties);
    }, retryDelay);
  }

  private clearRetryTimeout(): void {
    if (this.retryTimeoutId !== null) {
      window.clearTimeout(this.retryTimeoutId);
      this.retryTimeoutId = null;
    }
  }

  // Method to check if analytics is properly initialized
  public isReady(): boolean {
    return this.initialized && !!this.posthog && !this.config?.disabled;
  }

  // Method to get current configuration
  public getConfig(): AnalyticsConfig | null {
    return this.config;
  }
}

// Export singleton instance
export const analytics = AnalyticsService.getInstance();