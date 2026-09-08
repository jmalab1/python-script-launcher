import { signal } from '../vendor/standalone-preact.esm.js';

// App data (shared across components)
export const profiles = signal([]);
export const workflows = signal([]);
export const scriptStatusCache = signal({});

// UI state
export const PANELS = ['profiles', 'workflows', 'audit'];

function initialPanel() {
    const hash = location.hash.replace(/^#\/?/, '');
    if (PANELS.includes(hash)) return hash;
    const saved = localStorage.getItem('panel');
    return PANELS.includes(saved) ? saved : 'profiles';
}

export const currentPanel = signal(initialPanel());
export const theme = signal(localStorage.getItem('theme') || 'dark');
export const sidebarOpen = signal(false);

// History pagination (shared with Pagination component via pageSignal prop)
export const profileHistoryPage = signal(1);
export const workflowHistoryPage = signal(1);
export const profileHistoryData = signal(null);
export const workflowHistoryData = signal(null);

// Audit log
export const auditPage = signal(1);
export const auditData = signal(null);
export const auditAction = signal('');
export const auditEntity = signal('');

// Folders for grouping profiles and workflows
export const PROFILE_FOLDERS_KEY = 'profileFolders';
export const WORKFLOW_FOLDERS_KEY = 'workflowFolders';

function loadFolders(key) {
    try { return JSON.parse(localStorage.getItem(key)) || []; }
    catch { return []; }
}

export const profileFolders = signal(loadFolders(PROFILE_FOLDERS_KEY));
export const workflowFolders = signal(loadFolders(WORKFLOW_FOLDERS_KEY));

profileFolders.subscribe(v => localStorage.setItem(PROFILE_FOLDERS_KEY, JSON.stringify(v)));
workflowFolders.subscribe(v => localStorage.setItem(WORKFLOW_FOLDERS_KEY, JSON.stringify(v)));

export function addFolder(foldersSignal, name) {
    const id = 'folder_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
    foldersSignal.value = [...foldersSignal.value, { id, name: name.trim() }];
    return id;
}

export function renameFolder(foldersSignal, id, newName) {
    foldersSignal.value = foldersSignal.value.map(f => f.id === id ? { ...f, name: newName.trim() } : f);
}

export function deleteFolder(foldersSignal, id) {
    foldersSignal.value = foldersSignal.value.filter(f => f.id !== id);
}

export function reorderFolders(foldersSignal, next) {
    foldersSignal.value = next;
}

// Folder filter selection (null = show all, string = folder id, 'ungrouped' = items with no group)
export const selectedProfileFolder = signal(null);
export const selectedWorkflowFolder = signal(null);
