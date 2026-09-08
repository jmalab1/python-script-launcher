import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { formatTime, formatDuration, colorizeStatus } from '../utils.js';
import { Pagination } from './Pagination.js';
import { deleteHistoryEntry, deleteHistoryEntries } from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';
import { HistoryFilters, hasActiveFilters } from './ListFilters.js';

export function HistoryTable({ data, pageSignal, filters, onLoad, type, onOpenRun }) {
    const [pendingDelete, setPendingDelete] = useState(null);
    const [pendingBulkDelete, setPendingBulkDelete] = useState(null);
    const [selected, setSelected] = useState(new Set());

    if (!data || !data.entries || !data.entries.length) {
        const f = filters.value;
        const filtered = hasActiveFilters(f.name, f.status, f.since, f.until);
        return html`
            <div>
                <div class="mb-3">
                    <${HistoryFilters} filters=${filters} pageSignal=${pageSignal} onLoad=${onLoad} />
                </div>
                <div class="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                    ${filtered ? 'No runs match the current filters.' : `No ${type} run history yet.`}
                </div>
            </div>
        `;
    }

    async function confirmDelete() {
        if (!pendingDelete) return;
        await deleteHistoryEntry(pendingDelete.id);
        onLoad();
    }

    async function confirmBulkDelete() {
        if (!pendingBulkDelete) return;
        const ids = [...pendingBulkDelete];
        await deleteHistoryEntries(ids);
        setSelected(new Set());
        onLoad();
    }

    function toggleSelect(entryKey) {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(entryKey)) next.delete(entryKey);
            else next.add(entryKey);
            return next;
        });
    }

    function toggleSelectAll() {
        const allKeys = data.entries.map(e => e.id || e.run_id);
        const allSelected = allKeys.length > 0 && allKeys.every(k => selected.has(k));
        if (allSelected) {
            setSelected(new Set());
        } else {
            setSelected(new Set(allKeys));
        }
    }

    const allKeys = data.entries.map(e => e.id || e.run_id);
    const allSelected = allKeys.length > 0 && allKeys.every(k => selected.has(k));
    const someSelected = allKeys.some(k => selected.has(k));

    return html`
        <div class="flex flex-col h-full min-h-0">
            <div class="shrink-0 mb-2">
                <${HistoryFilters} filters=${filters} pageSignal=${pageSignal} onLoad=${onLoad} />
            </div>
            ${someSelected ? html`
                <div class="flex flex-wrap items-center gap-3 px-3 py-2 mb-2 bg-blue-50 dark:bg-blue-500/10 rounded-lg text-sm">
                    <span class="text-blue-700 dark:text-blue-300 font-medium">${selected.size} selected</span>
                    <button onClick=${() => setPendingBulkDelete(new Set(selected))}
                        class="px-3 py-1 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-lg transition">
                        Delete Selected
                    </button>
                    <button onClick=${() => setSelected(new Set())}
                        class="px-3 py-1 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">
                        Clear
                    </button>
                </div>
            ` : ''}
            <div class="overflow-auto -mx-3 px-3 flex-1 min-h-0">
                <table class="data-table w-full text-xs min-w-[600px]">
                    <thead>
                        <tr class="border-b border-gray-100 dark:border-gray-700/60">
                            <th class="w-8 py-2 px-1">
                                <input type="checkbox" checked=${allSelected} onChange=${toggleSelectAll}
                                    class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500 cursor-pointer" />
                            </th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">#</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Name</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Status</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Duration</th>
                            <th class="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Time</th>
                            <th class="w-8"></th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 dark:divide-gray-700/60">
                        ${data.entries.map((e, idx) => {
                            const stepsFailed = e.steps_total != null && e.steps_ok < e.steps_total;
                            const sc = colorizeStatus(e.status);
                            const rowId = (e.id || '').slice(0, 8) || '?';
                            const entryKey = e.id || e.run_id;
                            const isChecked = selected.has(entryKey);
                            return html`
                                <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition cursor-pointer ${isChecked ? 'bg-blue-50 dark:bg-blue-500/10' : ''}"
                                    title=${e.output_preview || ''}
                                    onClick=${() => onOpenRun(entryKey, e.name, type)}>
                                    <td class="py-2 px-1">
                                        <input type="checkbox" checked=${isChecked}
                                            onChange=${(ev) => { ev.stopPropagation(); toggleSelect(entryKey); }}
                                            onClick=${(ev) => ev.stopPropagation()}
                                            class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500 cursor-pointer" />
                                    </td>
                                    <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">${rowId}</td>
                                    <td class="py-2 px-3 font-medium text-gray-800 dark:text-gray-200">
                                        ${e.name}
                                        ${e.trigger === 'scheduled' ? html`<span class="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400 align-middle" title="Started by a schedule">Scheduled</span>` : ''}
                                    </td>
                                    <td class="py-2 px-3"><span class="inline-flex items-center gap-1.5 ${sc}">${e.status === 'running' ? html`<span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse"></span>` : ''}${e.status}</span></td>
                                    <td class="py-2 px-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                        ${formatDuration(e.duration)}${e.steps_total != null ? html` · <span class=${stepsFailed ? 'text-red-500 dark:text-red-400' : ''}>${e.steps_ok}/${e.steps_total} steps</span>` : ''}
                                    </td>
                                    <td class="py-2 px-3 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">${formatTime(e.started_at)}</td>
                                    <td class="py-2 px-1">
                                        <button onClick=${(ev) => { ev.stopPropagation(); setPendingDelete({ id: entryKey, name: e.name }); }}
                                            class="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition"
                                            title="Delete">
                                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                                        </button>
                                    </td>
                                </tr>
                            `;
                        })}
                    </tbody>
                </table>
            </div>
            <div class="shrink-0">
                <${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />
            </div>
            <${ConfirmModal} isOpen=${!!pendingDelete} onClose=${() => setPendingDelete(null)}
                onConfirm=${confirmDelete}
                title="Delete run"
                message=${html`This will permanently delete <span class="font-medium text-gray-700 dark:text-gray-200">${pendingDelete ? pendingDelete.name : ''}</span> from the run history. This action cannot be undone.`} />
            <${ConfirmModal} isOpen=${!!pendingBulkDelete} onClose=${() => setPendingBulkDelete(null)}
                onConfirm=${confirmBulkDelete}
                title="Delete selected runs"
                message=${html`This will permanently delete <span class="font-medium text-gray-700 dark:text-gray-200">${pendingBulkDelete ? pendingBulkDelete.size : 0} run${pendingBulkDelete && pendingBulkDelete.size !== 1 ? 's' : ''}</span> from the run history. This action cannot be undone.`} />
        </div>
    `;
}
