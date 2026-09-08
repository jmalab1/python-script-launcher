import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { addTag, renameTag, deleteTag, reorderTags } from '../state.js';
import { ConfirmModal } from './ConfirmModal.js';
import { ErrorBanner } from './ErrorBanner.js';

export function TagManager({ isOpen, onClose, tags, tagsSignal, profiles, workflows, saveProfile, saveWorkflow, reloadItems }) {
    const [newName, setNewName] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [editName, setEditName] = useState('');
    const [dragIndex, setDragIndex] = useState(null);
    const [overIndex, setOverIndex] = useState(null);
    const [pendingDelete, setPendingDelete] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        if (isOpen) setError('');
    }, [isOpen]);

    if (!isOpen) return null;

    // Tags are global, so usage counts span both profiles and workflows.
    const items = [...profiles, ...workflows];
    const hasTag = (item, id) => (item.tags || []).includes(id);

    const pendingTag = tags.find(f => f.id === pendingDelete);
    const pendingCount = pendingTag ? items.filter(item => hasTag(item, pendingTag.id)).length : 0;

    function handleCreate() {
        setError('');
        const trimmed = newName.trim();
        if (!trimmed) return;
        if (tags.some(f => f.name.toLowerCase() === trimmed.toLowerCase())) {
            setError('A tag with this name already exists.');
            return;
        }
        addTag(tagsSignal, trimmed);
        setNewName('');
    }

    function handleRename(id) {
        setError('');
        const trimmed = editName.trim();
        if (!trimmed) return;
        if (tags.some(f => f.id !== id && f.name.toLowerCase() === trimmed.toLowerCase())) {
            setError('A tag with this name already exists.');
            return;
        }
        renameTag(tagsSignal, id, trimmed);
        setEditingId(null);
        setEditName('');
    }

    function handleDelete(id) {
        setPendingDelete(id);
    }

    async function confirmDelete() {
        // Untag items before dropping the tag: if a save fails midway, the
        // tag still exists and no item is left pointing at a deleted tag
        // (which would land the item in an "Unknown" group).
        for (const item of profiles) {
            if (hasTag(item, pendingDelete)) {
                await saveProfile({ ...item, tags: item.tags.filter(t => t !== pendingDelete) });
            }
        }
        for (const item of workflows) {
            if (hasTag(item, pendingDelete)) {
                await saveWorkflow({ ...item, tags: item.tags.filter(t => t !== pendingDelete) });
            }
        }
        deleteTag(tagsSignal, pendingDelete);
        await reloadItems();
    }

    function handleDragStart(e, i) {
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', ''); } catch (err) {}
        setDragIndex(i);
    }

    function handleDragOver(e, i) {
        if (dragIndex === null) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (i !== overIndex) setOverIndex(i);
    }

    function handleDrop(e, i) {
        if (dragIndex === null || dragIndex === i) { setDragIndex(null); setOverIndex(null); return; }
        e.preventDefault();
        const next = tags.slice();
        const [moved] = next.splice(dragIndex, 1);
        next.splice(i, 0, moved);
        reorderTags(tagsSignal, next);
        setDragIndex(null);
        setOverIndex(null);
    }

    function handleDragEnd() {
        setDragIndex(null);
        setOverIndex(null);
    }

    function handleKeyDown(e, id) {
        if (e.key === 'Enter') handleRename(id);
        if (e.key === 'Escape') { setEditingId(null); setEditName(''); }
    }

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[85vh] overflow-y-auto border border-gray-200 dark:border-gray-700/60">
                    <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-t-2xl z-10">
                        <div class="flex items-center justify-between">
                            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">Manage Tags</h2>
                            <button onClick=${onClose} class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="px-6 py-5 space-y-4">
                        <${ErrorBanner} message=${error} />
                        <div class="flex gap-2">
                            <input type="text" value=${newName} onInput=${e => setNewName(e.target.value)}
                                onKeyDown=${e => e.key === 'Enter' && handleCreate()}
                                placeholder="New tag name"
                                class="flex-1 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                            <button onClick=${handleCreate}
                                class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg transition whitespace-nowrap">Add</button>
                        </div>
                        ${!tags.length ? html`
                            <div class="text-center py-6 text-gray-500 dark:text-gray-400 text-sm">
                                No tags yet. Create one above, then assign items to it when editing.
                            </div>
                        ` : html`
                            <div class="space-y-1.5">
                                ${tags.map((f, i) => {
                                    const count = items.filter(item => hasTag(item, f.id)).length;
                                    return html`
                                        <div key=${f.id}
                                            class="flex items-center gap-2 p-2 rounded-lg border transition ${dragIndex === i ? 'opacity-40' : ''} ${overIndex === i && dragIndex !== null && dragIndex !== i ? 'border-violet-400/70 ring-1 ring-violet-400/50' : 'border-gray-200 dark:border-gray-700/60'}"
                                            draggable=${dragIndex !== null}
                                            onDragStart=${(e) => handleDragStart(e, i)}
                                            onDragOver=${(e) => handleDragOver(e, i)}
                                            onDrop=${(e) => handleDrop(e, i)}
                                            onDragEnd=${handleDragEnd}
                                            onMouseUp=${() => setDragIndex(null)}>
                                            <div class="shrink-0 p-1 rounded cursor-grab active:cursor-grabbing text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition select-none"
                                                title="Drag to reorder"
                                                onMouseDown=${() => setDragIndex(i)}>
                                                <svg class="w-3 h-4" viewBox="0 0 10 16" fill="currentColor">
                                                    <circle cx="2.5" cy="2.5" r="1.4"/><circle cx="7.5" cy="2.5" r="1.4"/>
                                                    <circle cx="2.5" cy="8" r="1.4"/><circle cx="7.5" cy="8" r="1.4"/>
                                                    <circle cx="2.5" cy="13.5" r="1.4"/><circle cx="7.5" cy="13.5" r="1.4"/>
                                                </svg>
                                            </div>
                                            <svg class="w-4 h-4 text-amber-500 dark:text-amber-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/></svg>
                                            ${editingId === f.id ? html`
                                                <input type="text" value=${editName} onInput=${e => setEditName(e.target.value)}
                                                    onKeyDown=${(e) => handleKeyDown(e, f.id)}
                                                    onBlur=${() => handleRename(f.id)}
                                                    autoFocus
                                                    class="flex-1 min-w-0 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-sm text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                            ` : html`
                                                <span class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 truncate">${f.name}</span>
                                            `}
                                            <span class="text-[10px] text-gray-400 dark:text-gray-500 shrink-0">${count} item${count !== 1 ? 's' : ''}</span>
                                            ${editingId !== f.id ? html`
                                                <button onClick=${() => { setEditingId(f.id); setEditName(f.name); }}
                                                    class="p-1 text-gray-400 hover:text-violet-500 transition" title="Rename">
                                                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></svg>
                                                </button>
                                            ` : ''}
                                            <button onClick=${() => handleDelete(f.id)}
                                                class="p-1 text-gray-400 hover:text-red-500 transition" title="Delete tag">
                                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                                            </button>
                                        </div>
                                    `;
                                })}
                            </div>
                        `}
                    </div>
                    <div class="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-b-2xl flex justify-end">
                        <button onClick=${onClose} class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Done</button>
                    </div>
                </div>
            </div>
            <${ConfirmModal}
                isOpen=${!!pendingTag}
                onClose=${() => setPendingDelete(null)}
                onConfirm=${confirmDelete}
                title="Delete tag"
                message=${pendingCount
                    ? `Delete tag "${pendingTag.name}"? ${pendingCount} item${pendingCount !== 1 ? 's' : ''} will become untagged.`
                    : `Delete tag "${pendingTag.name}"?`}
            />
        </div>
    `;
}
