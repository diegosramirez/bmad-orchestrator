import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import './App.css';
import { PrivacyBanner, PrivacyIndicator } from './components/PrivacyBanner';
import {
  initializeAnalytics,
  usePageViewTracking,
  trackFeatureUsage,
  getAnalyticsHealth
} from './services/analytics';

// Example pages to demonstrate page view tracking
const HomePage: React.FC = () => {
  usePageViewTracking();

  const handleFeatureClick = () => {
    trackFeatureUsage('home_cta_button', { location: 'hero_section' });
  };

  return (
    <div className="page">
      <h1>Home Page</h1>
      <p>Welcome to the BMAD Orchestrator Analytics Demo</p>
      <button onClick={handleFeatureClick} data-track-label="Get Started CTA">
        Get Started
      </button>
      <nav>
        <Link to="/dashboard">Go to Dashboard</Link>
        <Link to="/settings">Go to Settings</Link>
      </nav>
    </div>
  );
};

const DashboardPage: React.FC = () => {
  usePageViewTracking();

  const handleDataExport = () => {
    trackFeatureUsage('data_export', { format: 'csv', source: 'dashboard' });
  };

  return (
    <div className="page">
      <h1>Dashboard Page</h1>
      <p>Analytics dashboard with tracked interactions</p>
      <button onClick={handleDataExport} data-track-label="Export Data">
        Export Data
      </button>
      <button data-track-label="Refresh Dashboard">Refresh</button>
      <nav>
        <Link to="/">Go to Home</Link>
        <Link to="/settings">Go to Settings</Link>
      </nav>
    </div>
  );
};

const SettingsPage: React.FC = () => {
  usePageViewTracking();
  const [analyticsHealth, setAnalyticsHealth] = useState<any>(null);

  useEffect(() => {
    setAnalyticsHealth(getAnalyticsHealth());
  }, []);

  const handlePrivacyManage = () => {
    alert('Privacy settings would open here in a real app');
  };

  return (
    <div className="page">
      <h1>Settings Page</h1>
      <p>Application settings and privacy controls</p>

      <div className="settings-section">
        <h3>Privacy Controls</h3>
        <PrivacyIndicator onManageClick={handlePrivacyManage} />
      </div>

      <div className="settings-section">
        <h3>Analytics Health</h3>
        <pre>{JSON.stringify(analyticsHealth, null, 2)}</pre>
      </div>

      <nav>
        <Link to="/">Go to Home</Link>
        <Link to="/dashboard">Go to Dashboard</Link>
      </nav>
    </div>
  );
};

const App: React.FC = () => {
  const [isAnalyticsInitialized, setIsAnalyticsInitialized] = useState(false);

  useEffect(() => {
    // Initialize analytics when the app loads
    const initAnalytics = async () => {
      try {
        await initializeAnalytics({
          apiKey: import.meta.env.VITE_POSTHOG_API_KEY || 'ph_test_key',
          host: import.meta.env.VITE_POSTHOG_HOST || 'https://app.posthog.com',
          disabled: !import.meta.env.VITE_POSTHOG_API_KEY // Disable if no API key
        });
        setIsAnalyticsInitialized(true);
      } catch (error) {
        console.error('Failed to initialize analytics:', error);
        setIsAnalyticsInitialized(true); // Still mark as initialized to show the app
      }
    };

    initAnalytics();
  }, []);

  const handleConsentChange = (consented: boolean) => {
    console.log('User consent changed:', consented);
  };

  if (!isAnalyticsInitialized) {
    return (
      <div className="loading">
        <p>Initializing analytics...</p>
      </div>
    );
  }

  return (
    <Router>
      <div className="app">
        <header className="app-header">
          <h1>BMAD Orchestrator</h1>
          <p>Analytics Integration Demo</p>
        </header>

        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>

        <footer className="app-footer">
          <p>&copy; 2026 BMAD Orchestrator - Privacy-First Analytics</p>
        </footer>

        {/* Privacy consent banner */}
        <PrivacyBanner
          onConsentChange={handleConsentChange}
          customMessage="We use PostHog analytics to understand how you use our orchestrator and improve your experience. You can opt out anytime."
          position="bottom"
          theme="light"
        />
      </div>
    </Router>
  );
};

export default App;