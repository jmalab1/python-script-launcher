import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { SortableList } from './SortableList.js';

export function GroupedSortableList({ items, folders, getFolder, onReorder, renderItem, selectedFolder, emptyMessage }) {
    const [collapsed, setCollapsed] = useState({});

    function toggleFolder(folderId) {
        setCollapsed(prev => ({ ...prev, [folderId]: !prev[folderId] }));
    }

    function folderName(folderId) {
        const f = folders.find(f => f.id === folderId);
        return f ? f.name : 'Unknown';
    }

    if (selectedFolder) {
        const filtered = items.filter(item => {
            const g = getFolder(item);
            return selectedFolder === 'ungrouped' ? !g : g === selectedFolder;
        });
        if (!filtered.length) {
            return html`<div class="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">${emptyMessage || 'No items in this folder.'}</div>`;
        }
        return html`
            <${SortableList}
                items=${filtered}
                onReorder=${onReorder}
                renderItem=${renderItem}
            />
        `;
    }

    const grouped = {};
    const ungrouped = [];
    for (const item of items) {
        const g = getFolder(item);
        if (!g) { ungrouped.push(item); continue; }
        if (!grouped[g]) grouped[g] = [];
        grouped[g].push(item);
    }

    const groupIds = Object.keys(grouped);
    const hasAnyGroups = groupIds.length > 0;

    function makeGroupReorderFn(groupItems, groupId) {
        return function handleGroupReorder(reorderedGroup) {
            const result = [];
            const reorderedSet = new Set(reorderedGroup);
            let ri = 0;
            for (const item of items) {
                if (groupId === '__ungrouped__' ? !getFolder(item) : getFolder(item) === groupId) {
                    result.push(reorderedGroup[ri++]);
                } else if (!reorderedSet.has(item)) {
                    result.push(item);
                }
            }
            onReorder(result);
        };
    }

    function renderSection(sectionItems, title, sectionKey, reorderFn) {
        const isCollapsed = collapsed[sectionKey];
        return html`
            <div class="mb-4">
                <button onClick=${() => toggleFolder(sectionKey)}
                    class="w-full flex items-center gap-2 px-1 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition select-none group">
                    <svg class="w-3 h-3 transition-transform ${isCollapsed ? '' : 'rotate-90'}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
                    <span class="uppercase tracking-wide">${title}</span>
                    <span class="text-[10px] text-gray-400 dark:text-gray-500 font-normal">(${sectionItems.length})</span>
                </button>
                <div class="${isCollapsed ? 'hidden' : ''}">
                    <${SortableList}
                        items=${sectionItems}
                        onReorder=${reorderFn}
                        renderItem=${renderItem}
                    />
                </div>
            </div>
        `;
    }

    if (!hasAnyGroups) {
        return html`
            <${SortableList}
                items=${items}
                onReorder=${onReorder}
                renderItem=${renderItem}
            />
        `;
    }

    return html`
        <div>
            ${ungrouped.length ? renderSection(ungrouped, 'Ungrouped', '__ungrouped__', makeGroupReorderFn(ungrouped, '__ungrouped__')) : ''}
            ${groupIds.map(gid => renderSection(grouped[gid], folderName(gid), gid, makeGroupReorderFn(grouped[gid], gid)))}
        </div>
    `;
}
