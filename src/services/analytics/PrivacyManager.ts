export interface ConsentState {
  accepted: boolean;
  version: string;
  timestamp: Date;
  sessionId: string;
}

export interface PrivacyPreferences {
  analytics: boolean;
  marketing: boolean;
  functional: boolean;
}

export type ConsentChangeCallback = (state: ConsentState) => void;

class PrivacyManager {
  private static instance: PrivacyManager;
  private static readonly STORAGE_KEY = 'bmad_privacy_consent';
  private static readonly CURRENT_VERSION = '1.0.0';

  private consentState: ConsentState | null = null;
  private callbacks: Set<ConsentChangeCallback> = new Set();
  private sessionId: string;

  private constructor() {
    this.sessionId = this.generateSessionId();
    this.loadConsentState();
  }

  public static getInstance(): PrivacyManager {
    if (!PrivacyManager.instance) {
      PrivacyManager.instance = new PrivacyManager();
    }
    return PrivacyManager.instance;
  }

  public getConsentState(): ConsentState | null {
    return this.consentState;
  }

  public isConsentRequired(): boolean {
    // Check if consent is required (no existing consent or version mismatch)
    if (!this.consentState) {
      return true;
    }

    // Check if consent version is outdated
    return this.consentState.version !== PrivacyManager.CURRENT_VERSION;
  }

  public hasConsented(): boolean {
    return this.consentState?.accepted === true && !this.isConsentRequired();
  }

  public acceptConsent(): void {
    const newState: ConsentState = {
      accepted: true,
      version: PrivacyManager.CURRENT_VERSION,
      timestamp: new Date(),
      sessionId: this.sessionId
    };

    this.updateConsentState(newState);
  }

  public declineConsent(): void {
    const newState: ConsentState = {
      accepted: false,
      version: PrivacyManager.CURRENT_VERSION,
      timestamp: new Date(),
      sessionId: this.sessionId
    };

    this.updateConsentState(newState);
  }

  public revokeConsent(): void {
    // Update consent state to declined
    if (this.consentState) {
      const revokedState: ConsentState = {
        ...this.consentState,
        accepted: false,
        timestamp: new Date()
      };
      this.updateConsentState(revokedState);
    }
  }

  public clearConsent(): void {
    try {
      localStorage.removeItem(PrivacyManager.STORAGE_KEY);
      this.consentState = null;
      this.notifyCallbacks();
    } catch (error) {
      console.error('[PrivacyManager] Failed to clear consent:', error);
    }
  }

  public onConsentChange(callback: ConsentChangeCallback): () => void {
    this.callbacks.add(callback);

    // Return unsubscribe function
    return () => {
      this.callbacks.delete(callback);
    };
  }

  public getSessionId(): string {
    return this.sessionId;
  }

  public refreshSession(): void {
    this.sessionId = this.generateSessionId();

    // Update session ID in consent state if it exists
    if (this.consentState) {
      const updatedState: ConsentState = {
        ...this.consentState,
        sessionId: this.sessionId
      };
      this.updateConsentState(updatedState, false); // Don't notify callbacks for session refresh
    }
  }

  public getConsentVersion(): string {
    return PrivacyManager.CURRENT_VERSION;
  }

  public exportConsentData(): string {
    // Export consent data for user visibility/download
    const data = {
      consentState: this.consentState,
      exportTimestamp: new Date().toISOString(),
      version: PrivacyManager.CURRENT_VERSION
    };

    return JSON.stringify(data, null, 2);
  }

  // Check if consent has expired (optional: implement expiration logic)
  public isConsentExpired(): boolean {
    if (!this.consentState) {
      return true;
    }

    // Example: consent expires after 1 year
    const expirationTime = 365 * 24 * 60 * 60 * 1000; // 1 year in milliseconds
    const consentAge = Date.now() - new Date(this.consentState.timestamp).getTime();

    return consentAge > expirationTime;
  }

  private updateConsentState(newState: ConsentState, notify: boolean = true): void {
    this.consentState = newState;
    this.saveConsentState();

    if (notify) {
      this.notifyCallbacks();
    }
  }

  private loadConsentState(): void {
    try {
      const stored = localStorage.getItem(PrivacyManager.STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);

        // Validate the stored data structure
        if (this.isValidConsentState(parsed)) {
          this.consentState = {
            ...parsed,
            timestamp: new Date(parsed.timestamp) // Convert string back to Date
          };
        } else {
          console.warn('[PrivacyManager] Invalid stored consent state, clearing...');
          this.clearConsent();
        }
      }
    } catch (error) {
      console.error('[PrivacyManager] Failed to load consent state:', error);
      this.clearConsent();
    }
  }

  private saveConsentState(): void {
    if (!this.consentState) {
      return;
    }

    try {
      const serialized = JSON.stringify(this.consentState);
      localStorage.setItem(PrivacyManager.STORAGE_KEY, serialized);
    } catch (error) {
      console.error('[PrivacyManager] Failed to save consent state:', error);
    }
  }

  private notifyCallbacks(): void {
    if (this.consentState) {
      this.callbacks.forEach(callback => {
        try {
          callback(this.consentState!);
        } catch (error) {
          console.error('[PrivacyManager] Callback error:', error);
        }
      });
    }
  }

  private isValidConsentState(state: any): boolean {
    return (
      typeof state === 'object' &&
      typeof state.accepted === 'boolean' &&
      typeof state.version === 'string' &&
      typeof state.timestamp === 'string' &&
      typeof state.sessionId === 'string'
    );
  }

  private generateSessionId(): string {
    // Generate a unique session ID
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2);
    return `session_${timestamp}_${random}`;
  }

  // Method to check if consent is required across domains/subdomains
  public isSubdomainConsentValid(_domain: string): boolean {
    if (!this.consentState) {
      return false;
    }

    // This could be extended to handle cross-subdomain consent
    // For now, assume consent is valid across subdomains of the same domain
    return true;
  }

  // Method to sync consent across multiple tabs
  public syncAcrossTabs(): () => void {
    // Listen for storage changes to sync consent across tabs
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === PrivacyManager.STORAGE_KEY) {
        if (event.newValue) {
          try {
            const parsed = JSON.parse(event.newValue);
            if (this.isValidConsentState(parsed)) {
              this.consentState = {
                ...parsed,
                timestamp: new Date(parsed.timestamp)
              };
              this.notifyCallbacks();
            }
          } catch (error) {
            console.error('[PrivacyManager] Failed to sync consent from storage:', error);
          }
        } else {
          // Consent was cleared in another tab
          this.consentState = null;
          this.notifyCallbacks();
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);

    // Return cleanup function
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }
}

// Export singleton instance
export const privacyManager = PrivacyManager.getInstance();