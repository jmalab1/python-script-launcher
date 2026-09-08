import { signal } from '../vendor/standalone-preact.esm.js';

// App data (shared across components)
export const profiles = signal([]);
export const workflows = signal([]);
export const schedules = signal([]);
export const scriptStatusCache = signal({});

// UI state
export const PANELS = ['profiles', 'workflows', 'schedules', 'audit', 'logs'];

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

// History search filters. Dates are 'YYYY-MM-DD' strings ('' = unset) so
// the browser date inputs can hold them directly; api.js converts them
// to epoch seconds for the server.
export const profileHistoryFilters = signal({ name: '', status: '', since: '', until: '' });
export const workflowHistoryFilters = signal({ name: '', status: '', since: '', until: '' });

// Audit log
export const auditPage = signal(1);
export const auditData = signal(null);
export const auditAction = signal('');
export const auditEntity = signal('');
export const auditName = signal('');
export const auditSince = signal('');
export const auditUntil = signal('');

// Server log viewer
export const logData = signal([]);
export const logOffset = signal(0);

// Tags for grouping profiles and workflows
export const TRASH_GROUP = '__trash__';
export const PROFILE_TAGS_KEY = 'profileTags';
export const WORKFLOW_TAGS_KEY = 'workflowTags';

function loadTags(key, legacyKey) {
    try {
        const raw = localStorage.getItem(key) || (legacyKey ? localStorage.getItem(legacyKey) : null);
        return raw ? JSON.parse(raw) : [];
    } catch { return []; }
}

export const profileTags = signal(loadTags(PROFILE_TAGS_KEY, 'profileFolders'));
export const workflowTags = signal(loadTags(WORKFLOW_TAGS_KEY, 'workflowFolders'));

profileTags.subscribe(v => localStorage.setItem(PROFILE_TAGS_KEY, JSON.stringify(v)));
workflowTags.subscribe(v => localStorage.setItem(WORKFLOW_TAGS_KEY, JSON.stringify(v)));

export function addTag(tagsSignal, name) {
    const id = 'tag_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
    tagsSignal.value = [...tagsSignal.value, { id, name: name.trim() }];
    return id;
}

export function renameTag(tagsSignal, id, newName) {
    tagsSignal.value = tagsSignal.value.map(t => t.id === id ? { ...t, name: newName.trim() } : t);
}

export function deleteTag(tagsSignal, id) {
    tagsSignal.value = tagsSignal.value.filter(t => t.id !== id);
}

export function reorderTags(tagsSignal, next) {
    tagsSignal.value = next;
}

// Tag filter selection (null = show all, string = tag id, 'untagged' = items with no tag)
export const selectedProfileTag = signal(null);
export const selectedWorkflowTag = signal(null);
