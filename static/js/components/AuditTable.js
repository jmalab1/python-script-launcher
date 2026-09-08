import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { esc, formatTime } from '../utils.js';
import { Pagination } from './Pagination.js';
import { auditPage, auditAction, auditEntity, auditName, auditSince, auditUntil } from '../state.js';
import { fetchAuditDetail } from '../api.js';
import { SearchInput, DateInputs, hasActiveFilters } from './ListFilters.js';

function formatAuditTime(ts) {
    return ts ? new Date(ts * 1000).toLocaleString() : '-';
}

const ACTION_STYLES = {
    created: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-500/10',
    updated: 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-500/10',
    deleted: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10',
    reordered: 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700/40',
    restored: 'text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10',
};

function actionLabel(action) {
    return action ? action.charAt(0).toUpperCase() + action.slice(1) : '';
}

function entryDetails(e) {
    const d = e.details || {};
    if (e.action === 'updated' && Array.isArray(d.changed) && d.changed.length) {
        return 'Changed: ' + d.changed.join(', ');
    }
    if (d.duplicate_of) return 'Duplicate of "' + d.duplicate_of + '"';
    if (e.action === 'restored') return 'Restored from trash';
    if (e.action === 'reordered' && Array.isArray(d.order)) {
        return 'New order: ' + d.order.length + ' items';
    }
    return '—';
}

function AuditDetailModal({ entry, onClose }) {
    if (!entry) return null;
    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl border border-gray-200 dark:border-gray-700/60 p-6 max-h-[85vh] flex flex-col">
                    <div class="flex items-start justify-between gap-4">
                        <div class="min-w-0">
                            <div class="flex items-center gap-2 flex-wrap">
                                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_STYLES[entry.action] || ''}">${actionLabel(entry.action)}</span>
                                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700/40">${esc(entry.entity_type)}</span>
                                <span class="text-sm text-gray-500 dark:text-gray-400">${formatAuditTime(entry.timestamp)}</span>
                            </div>
                            <h3 class="mt-2 text-base font-semibold text-gray-800 dark:text-gray-100 truncate">${esc(entry.name || '')}</h3>
                        </div>
                        <button onClick=${onClose}
                            class="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
                        </button>
                    </div>
                    <div class="mt-4 overflow-y-auto space-y-4">
                        ${entry.details ? html`
                            <div>
                                <h4 class="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 mb-1">Details</h4>
                                <pre class="text-xs bg-gray-50 dark:bg-gray-900/60 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">${esc(JSON.stringify(entry.details, null, 2))}</pre>
                            </div>
                        ` : ''}
                        ${entry.before ? html`
                            <div>
                                <h4 class="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 mb-1">Before</h4>
                                <pre class="text-xs bg-gray-50 dark:bg-gray-900/60 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">${esc(JSON.stringify(entry.before, null, 2))}</pre>
                            </div>
                        ` : ''}
                        ${entry.after ? html`
                            <div>
                                <h4 class="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 mb-1">After</h4>
                                <pre class="text-xs bg-gray-50 dark:bg-gray-900/60 rounded-lg p-3 overflow-x-auto text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">${esc(JSON.stringify(entry.after, null, 2))}</pre>
                            </div>
                        ` : ''}
                    </div>
                    <div class="mt-5 flex justify-end gap-2">
                        <button onClick=${onClose}
                            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

export function AuditTable({ data, pageSignal, onLoad }) {
    const [detail, setDetail] = useState(null);

    if (!data || !data.entries || !data.entries.length) {
        const filtered = hasActiveFilters(auditAction.value, auditEntity.value, auditName.value, auditSince.value, auditUntil.value);
        return html`
            <div>
                <div class="flex items-center justify-between gap-3 mb-3">
                    <${AuditFilters} onLoad=${onLoad} />
                </div>
                <div class="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                    ${filtered ? 'No audit entries match the current filters.' : 'No audit entries yet.'}
                </div>
            </div>
        `;
    }

    async function openDetail(e) {
        const full = await fetchAuditDetail(e.id);
        setDetail(full);
    }

    return html`
        <div class="flex flex-col h-full min-h-0">
            <div class="flex items-center justify-between gap-3 mb-3 shrink-0">
                <${AuditFilters} onLoad=${onLoad} />
            </div>
            <div class="overflow-auto -mx-3 px-3 flex-1 min-h-0">
                <table class="w-full text-xs min-w-[640px]">
                    <thead>
                        <tr class="border-b border-gray-100 dark:border-gray-700/60">
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">#</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Entity</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Name</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Action</th>
                            <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Details</th>
                            <th class="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Time</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 dark:divide-gray-700/60">
                        ${data.entries.map((e, idx) => {
                            const rowNum = data.total - (data.page - 1) * data.per_page - idx;
                            const as = ACTION_STYLES[e.action] || '';
                            return html`
                                <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition cursor-pointer"
                                    onClick=${() => openDetail(e)}>
                                    <td class="py-2 px-3 text-gray-400">${rowNum}</td>
                                    <td class="py-2 px-3">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700/40 capitalize">${esc(e.entity_type)}</span>
                                    </td>
                                    <td class="py-2 px-3 font-medium text-gray-800 dark:text-gray-200">${esc(e.name)}</td>
                                    <td class="py-2 px-3">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${as}">${actionLabel(e.action)}</span>
                                    </td>
                                    <td class="py-2 px-3 text-gray-500 dark:text-gray-400 max-w-[16rem] truncate" title=${esc(entryDetails(e))}>${entryDetails(e)}</td>
                                    <td class="py-2 px-3 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">${formatTime(e.timestamp)}</td>
                                </tr>
                            `;
                        })}
                    </tbody>
                </table>
            </div>
            <div class="shrink-0">
                <${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />
            </div>
            <${AuditDetailModal} entry=${detail} onClose=${() => setDetail(null)} />
        </div>
    `;
}

export function AuditFilters({ onLoad }) {
    function update(signal, value) {
        signal.value = value;
        auditPage.value = 1;
        onLoad();
    }

    function clearAll() {
        auditAction.value = '';
        auditEntity.value = '';
        auditName.value = '';
        auditSince.value = '';
        auditUntil.value = '';
        auditPage.value = 1;
        onLoad();
    }

    const active = hasActiveFilters(auditAction.value, auditEntity.value, auditName.value, auditSince.value, auditUntil.value);

    return html`
        <div class="flex flex-wrap items-center gap-2">
            <${SearchInput} value=${auditName.value} onCommit=${(name) => update(auditName, name)} />
            <select value=${auditAction.value}
                onChange=${(ev) => update(auditAction, ev.target.value)}
                class="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300">
                <option value="">All actions</option>
                <option value="created">Created</option>
                <option value="updated">Updated</option>
                <option value="deleted">Deleted</option>
                <option value="reordered">Reordered</option>
                <option value="restored">Restored</option>
                <option value="run_now">Run now</option>
            </select>
            <select value=${auditEntity.value}
                onChange=${(ev) => update(auditEntity, ev.target.value)}
                class="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300">
                <option value="">All entities</option>
                <option value="profile">Profiles</option>
                <option value="workflow">Workflows</option>
                <option value="schedule">Schedules</option>
            </select>
            <${DateInputs} since=${auditSince.value} until=${auditUntil.value}
                onSince=${(since) => update(auditSince, since)}
                onUntil=${(until) => update(auditUntil, until)} />
            ${active ? html`
                <button onClick=${clearAll}
                    class="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 px-2 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                    Clear
                </button>
            ` : ''}
        </div>
    `;
}
