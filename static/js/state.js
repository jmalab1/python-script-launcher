import { signal } from '../vendor/standalone-preact.esm.js';

// App data (shared across components)
export const profiles = signal([]);
export const workflows = signal([]);
export const scriptStatusCache = signal({});

// UI state
export const currentPanel = signal('profiles');
export const theme = signal(localStorage.getItem('theme') || 'dark');
export const sidebarOpen = signal(false);

// History pagination (shared with Pagination component via pageSignal prop)
export const profileHistoryPage = signal(1);
export const workflowHistoryPage = signal(1);
export const profileHistoryData = signal(null);
export const workflowHistoryData = signal(null);
