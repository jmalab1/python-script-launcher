import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { TRASH_GROUP } from '../state.js';
import { SortableList } from './SortableList.js';

// Flat, drag-sortable list with a collapsible Trash section at the bottom.
// Items can carry several tags, so there are no per-tag sections — use the
// tag filter pills to narrow the list instead.
export function ItemList({ items, getTags, selectedTag, onReorder, renderItem, emptyMessage }) {
    const [collapsed, setCollapsed] = useState({ [TRASH_GROUP]: true });

    function toggleSection(sectionKey) {
        setCollapsed(prev => ({ ...prev, [sectionKey]: !prev[sectionKey] }));
    }

    const mainItems = [];
    const trashItems = [];
    for (const item of items) {
        if ((item.group || '') === TRASH_GROUP) trashItems.push(item);
        else mainItems.push(item);
    }

    let visible = mainItems;
    if (selectedTag) {
        visible = mainItems.filter(item => {
            const itemTagIds = getTags(item);
            if (selectedTag === 'untagged') return itemTagIds.length === 0;
            return itemTagIds.includes(selectedTag);
        });
        if (!visible.length) {
            return html`<div class="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">${emptyMessage || 'No items with this tag.'}</div>`;
        }
    }

    function handleReorder(reorderedSubset) {
        // Dragging while a filter is active only moves the visible items;
        // splice them back into their old slots so hidden items keep
        // their positions.
        const subsetIds = new Set(visible.map(item => item.id));
        let k = 0;
        onReorder(items.map(item => subsetIds.has(item.id) ? reorderedSubset[k++] : item));
    }

    function renderTrashSection() {
        const isCollapsed = collapsed[TRASH_GROUP];
        return html`
            <div class="mb-4">
                <button onClick=${() => toggleSection(TRASH_GROUP)}
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

    return html`
        <${SortableList} items=${visible} onReorder=${handleReorder} renderItem=${renderItem} />
        ${renderTrashSection()}
    `;
}
