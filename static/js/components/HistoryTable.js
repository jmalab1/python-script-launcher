import { html } from '../../vendor/standalone-preact.esm.js';
import { esc, formatTime, colorizeStatus } from '../utils.js';
import { Pagination } from './Pagination.js';
import { deleteHistoryEntry } from '../api.js';

export function HistoryTable({ data, pageSignal, onLoad, type, onOpenRun }) {
    if (!data || !data.entries || !data.entries.length) {
        return html`
            <div class="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                No ${type} run history yet.
            </div>
        `;
    }

    async function handleDelete(runId) {
        await deleteHistoryEntry(runId);
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
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Output</th>
                        <th class="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Time</th>
                        <th class="w-8"></th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100 dark:divide-gray-700/60">
                    ${data.entries.map((e, idx) => {
                        const preview = (e.output_preview || '').replace(/\n/g, ' ').substring(0, 60);
                        const sc = colorizeStatus(e.status);
                        const rowNum = data.total - (data.page - 1) * data.per_page - idx;
                        return html`
                            <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition cursor-pointer"
                                title=${esc(e.output_preview || '')}
                                onClick=${() => onOpenRun(e.run_id, e.name, type)}>
                                <td class="py-2 px-3 text-gray-400">${rowNum}</td>
                                <td class="py-2 px-3 font-medium text-gray-800 dark:text-gray-200">${esc(e.name)}</td>
                                <td class="py-2 px-3"><span class=${sc}>${e.status}</span></td>
                                <td class="py-2 px-3 text-gray-500 dark:text-gray-400 font-mono truncate max-w-[200px]">${esc(preview)}</td>
                                <td class="py-2 px-3 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">${formatTime(e.started_at)}</td>
                                <td class="py-2 px-1">
                                    <button onClick=${(ev) => { ev.stopPropagation(); handleDelete(e.run_id); }}
                                        class="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition"
                                        title="Delete">
                                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                                    </button>
                                </td>
                            </tr>
                        `;
                    })}
                </tbody>
            </table>
            <${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />
        </div>
    `;
}
