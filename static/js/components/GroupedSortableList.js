import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { TRASH_GROUP } from '../state.js';
import { SortableList } from './SortableList.js';

export function GroupedSortableList({ items, tags, getTag, onReorder, renderItem, selectedTag, emptyMessage }) {
    const [collapsed, setCollapsed] = useState({ [TRASH_GROUP]: true });

    function toggleTag(tagId) {
        setCollapsed(prev => ({ ...prev, [tagId]: !prev[tagId] }));
    }

    function tagLabel(tagId) {
        const f = tags.find(f => f.id === tagId);
        return f ? f.name : 'Unknown';
    }

    if (selectedTag) {
        const filtered = items.filter(item => {
            const g = getTag(item);
            if (selectedTag === 'untagged') return !g;
            if (selectedTag === TRASH_GROUP) return g === TRASH_GROUP;
            return g === selectedTag;
        });
        if (!filtered.length) {
            return html`<div class="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">${emptyMessage || 'No items with this tag.'}</div>`;
        }
        return html`
            <${SortableList}
                items=${filtered}
                onReorder=${selectedTag === TRASH_GROUP ? () => {} : onReorder}
                renderItem=${renderItem}
            />
        `;
    }

    const grouped = {};
    const untagged = [];
    const trashItems = [];
    for (const item of items) {
        const g = getTag(item);
        if (g === TRASH_GROUP) { trashItems.push(item); continue; }
        if (!g) { untagged.push(item); continue; }
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
                if (groupId === '__untagged__' ? !getTag(item) : getTag(item) === groupId) {
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
                <button onClick=${() => toggleTag(sectionKey)}
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

    function renderTrashSection() {
        const isCollapsed = collapsed[TRASH_GROUP];
        return html`
            <div class="mb-4">
                <button onClick=${() => toggleTag(TRASH_GROUP)}
                    class="w-full flex items-center gap-2 px-1 py-1.5 text-xs font-medium text-red-400 dark:text-red-500 hover:text-red-600 dark:hover:text-red-400 transition select-none group">
                    <svg class="w-3 h-3 transition-transform ${isCollapsed ? '' : 'rotate-90'}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
                    <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                    <span class="uppercase tracking-wide">Trash</span>
                    <span class="text-[10px] text-red-400/70 dark:text-red-500/70 font-normal">(${trashItems.length})</span>
                </button>
                <div class="${isCollapsed ? 'hidden' : ''}">
                    ${trashItems.length ? html`
                        <${SortableList}
                            items=${trashItems}
                            onReorder=${() => {}}
                            renderItem=${renderItem}
                        />
                    ` : html`
                        <div class="px-1 py-2 text-xs text-gray-400 dark:text-gray-500">Trash is empty.</div>
                    `}
                </div>
            </div>
        `;
    }

    if (!hasAnyGroups) {
        return html`
            <${SortableList}
                items=${untagged}
                onReorder=${onReorder}
                renderItem=${renderItem}
            />
            ${renderTrashSection()}
        `;
    }

    return html`
        <div>
            ${untagged.length ? renderSection(untagged, 'Untagged', '__untagged__', makeGroupReorderFn(untagged, '__untagged__')) : ''}
            ${groupIds.map(gid => renderSection(grouped[gid], tagLabel(gid), gid, makeGroupReorderFn(grouped[gid], gid)))}
            ${renderTrashSection()}
        </div>
    `;
}
