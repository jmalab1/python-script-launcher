import { html } from '../../vendor/standalone-preact.esm.js';

export function FolderFilter({ folders, items, getFolder, selectedFolder, onSelect }) {
    const folderCounts = {};
    let ungroupedCount = 0;
    for (const item of items) {
        const g = getFolder(item);
        if (g) {
            folderCounts[g] = (folderCounts[g] || 0) + 1;
        } else {
            ungroupedCount++;
        }
    }

    const activeGroups = folders.filter(f => folderCounts[f.id]);
    const hasAnyItems = items.length > 0;
    const hasAnyGroups = activeGroups.length > 0 || ungroupedCount > 0;

    if (!hasAnyItems || !hasAnyGroups) return null;

    function Pill(label, count, value, icon) {
        const isActive = selectedFolder === value;
        return html`
            <button onClick=${() => onSelect(isActive ? null : value)}
                class="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition whitespace-nowrap ${isActive
                    ? 'bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-500/30'
                    : 'bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400 border border-transparent hover:border-gray-200 dark:hover:border-gray-600'}">
                ${icon ? html`<span class="text-[10px]">${icon}</span>` : ''}
                ${label}
                <span class="text-[10px] opacity-70">${count}</span>
            </button>
        `;
    }

    return html`
        <div class="flex flex-wrap gap-1.5 mb-3">
            ${Pill('All', items.length, null, null)}
            ${ungroupedCount ? Pill('Ungrouped', ungroupedCount, 'ungrouped', html`<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z"/></svg>`) : ''}
            ${activeGroups.map(f => Pill(f.name, folderCounts[f.id], f.id, html`<svg class="w-3 h-3 text-amber-500" fill="currentColor" viewBox="0 0 20 20"><path d="M3.75 3a.75.75 0 00-.75.75v12.5c0 .414.336.75.75.75h12.5a.75.75 0 00.75-.75V6.75a.75.75 0 00-.75-.75H3.75zM3 6.75A.75.75 0 013.75 6h4.5a.75.75 0 01.75.75v4.5a.75.75 0 01-.75.75h-4.5A.75.75 0 013 11.25v-4.5z"/></svg>`))}
        </div>
    `;
}
