import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';

export function SortableList({ items, onReorder, renderItem, getKey, gripClass, gapClass }) {
    const [dragIndex, setDragIndex] = useState(null);
    const [armedIndex, setArmedIndex] = useState(null);
    const [overIndex, setOverIndex] = useState(null);

    const keyOf = getKey || (item => item.id);

    function reset() {
        setDragIndex(null);
        setArmedIndex(null);
        setOverIndex(null);
    }

    function handleDragStart(e, i) {
        e.stopPropagation();
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', ''); } catch (err) {}
        setDragIndex(i);
    }

    function handleDragOver(e, i) {
        if (dragIndex === null) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        if (i !== overIndex) setOverIndex(i);
    }

    function handleDrop(e, i) {
        if (dragIndex === null) return;
        e.preventDefault();
        e.stopPropagation();
        if (dragIndex === i) { reset(); return; }
        const next = items.slice();
        const [moved] = next.splice(dragIndex, 1);
        next.splice(i, 0, moved);
        onReorder(next);
        reset();
    }

    return html`
        <div class="${gapClass || 'space-y-3'}">
            ${items.map((item, i) => html`
                <div
                    key=${keyOf(item)}
                    class="flex items-start gap-1.5 ${dragIndex === i ? 'opacity-40' : ''}"
                    draggable=${armedIndex === i}
                    onDragStart=${(e) => handleDragStart(e, i)}
                    onDragOver=${(e) => handleDragOver(e, i)}
                    onDrop=${(e) => handleDrop(e, i)}
                    onDragEnd=${reset}
                    onMouseUp=${() => setArmedIndex(null)}
                >
                    <div
                        class="shrink-0 ${gripClass || 'mt-4'} p-1 rounded cursor-grab active:cursor-grabbing text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition select-none"
                        title="Drag to reorder"
                        onMouseDown=${() => setArmedIndex(i)}
                    >
                        <svg class="w-3 h-4" viewBox="0 0 10 16" fill="currentColor">
                            <circle cx="2.5" cy="2.5" r="1.4"/><circle cx="7.5" cy="2.5" r="1.4"/>
                            <circle cx="2.5" cy="8" r="1.4"/><circle cx="7.5" cy="8" r="1.4"/>
                            <circle cx="2.5" cy="13.5" r="1.4"/><circle cx="7.5" cy="13.5" r="1.4"/>
                        </svg>
                    </div>
                    <div class="flex-1 min-w-0 rounded-xl transition ${overIndex === i && dragIndex !== null && dragIndex !== i ? 'ring-2 ring-violet-400/70' : ''}">
                        ${renderItem(item, i)}
                    </div>
                </div>
            `)}
        </div>
    `;
}
