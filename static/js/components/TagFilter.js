import { html } from '../../vendor/standalone-preact.esm.js';
import { TRASH_GROUP } from '../state.js';

const TAG_ICON = html`<svg class="w-3 h-3 text-amber-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/></svg>`;

export function TagFilter({ tags, items, getTags, selectedTag, onSelect }) {
    const tagCounts = {};
    let untaggedCount = 0;
    for (const item of items) {
        // Trash items are listed in their own section, never in the pills.
        if ((item.group || '') === TRASH_GROUP) continue;
        const itemTagIds = getTags(item);
        if (itemTagIds.length) {
            for (const id of itemTagIds) {
                tagCounts[id] = (tagCounts[id] || 0) + 1;
            }
        } else {
            untaggedCount++;
        }
    }

    const activeTags = tags.filter(f => tagCounts[f.id]);
    const hasAnyItems = items.length > 0;
    const hasAnyTags = activeTags.length > 0 || untaggedCount > 0;

    if (!hasAnyItems || !hasAnyTags) return null;

    function Pill(label, count, value, icon) {
        const isActive = selectedTag === value;
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
        <div class="sticky top-0 z-10 flex flex-wrap gap-1.5 mb-3 bg-gray-50 dark:bg-gray-900 -mx-1 px-1 -my-1 py-1">
            ${Pill('All', items.length, null, null)}
            ${untaggedCount ? Pill('Untagged', untaggedCount, 'untagged', html`<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z"/></svg>`) : ''}
            ${activeTags.map(f => Pill(f.name, tagCounts[f.id], f.id, TAG_ICON))}
        </div>
    `;
}
