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

// Tags for grouping profiles and workflows. One global list: both kinds of
// item reference the same tags by id.
export const TRASH_GROUP = '__trash__';
export const TAGS_KEY = 'tags';
// Older versions kept a separate list per panel (and earlier still, per
// panel "folders"). They are merged into the single global list on load.
const LEGACY_TAG_KEYS = ['profileTags', 'profileFolders', 'workflowTags', 'workflowFolders'];

function loadTags() {
    const read = (key) => {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : [];
        } catch { return []; }
    };
    const merged = [];
    const seen = new Set();
    for (const tag of [read(TAGS_KEY), ...LEGACY_TAG_KEYS.map(read)].flat()) {
        if (!tag || !tag.id || seen.has(tag.id)) continue;
        seen.add(tag.id);
        merged.push(tag);
    }
    return merged;
}

export const tags = signal(loadTags());

tags.subscribe(v => localStorage.setItem(TAGS_KEY, JSON.stringify(v)));

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
