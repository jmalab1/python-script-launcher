import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { esc, formatTime, formatDuration, colorizeStatus } from '../utils.js';
import { Pagination } from './Pagination.js';
import { deleteHistoryEntry } from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';

export function HistoryTable({ data, pageSignal, onLoad, type, onOpenRun }) {
    const [pendingDelete, setPendingDelete] = useState(null);

    if (!data || !data.entries || !data.entries.length) {
        return html`
            <div class="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                No ${type} run history yet.
            </div>
        `;
    }

    async function confirmDelete() {
        if (!pendingDelete) return;
        await deleteHistoryEntry(pendingDelete.id);
        onLoad();
    }

    return html`
        <div>
            <table class="w-full text-xs">
                <thead>
                    <tr class="border-b border-gray-100 dark:border-gray-700/60">
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
                        const rowNum = data.total - (data.page - 1) * data.per_page - idx;
                        const entryKey = e.id || e.run_id;
                        return html`
                            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition cursor-pointer"
                                title=${esc(e.output_preview || '')}
                                onClick=${() => onOpenRun(entryKey, e.name, type)}>
                                <td class="py-2 px-3 text-gray-400">${rowNum}</td>
                                <td class="py-2 px-3 font-medium text-gray-800 dark:text-gray-200">${esc(e.name)}</td>
                                <td class="py-2 px-3"><span class=${sc}>${e.status}</span></td>
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
            <${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />
            <${ConfirmModal} isOpen=${!!pendingDelete} onClose=${() => setPendingDelete(null)}
                onConfirm=${confirmDelete}
                title="Delete run"
                message=${html`This will permanently delete <span class="font-medium text-gray-700 dark:text-gray-200">${esc(pendingDelete ? pendingDelete.name : '')}</span> from the run history. This action cannot be undone.`} />
        </div>
    `;
}
