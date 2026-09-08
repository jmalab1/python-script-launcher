import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { esc, formatTime } from '../utils.js';
import { Pagination } from './Pagination.js';
import { ConfirmModal } from './ConfirmModal.js';
import { auditPage, auditAction, auditEntity } from '../state.js';
import { fetchAuditDetail, deleteAuditEntry, restoreAuditEntry } from '../api.js';

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
    if (e.action === 'restored') return 'Restored from earlier delete';
    if (e.action === 'reordered' && Array.isArray(d.order)) {
        return 'New order: ' + d.order.length + ' items';
    }
    return '—';
}

function AuditDetailModal({ entry, onClose, onRestore }) {
    if (!entry) return null;
    const deletable = entry.action === 'deleted' && entry.before;
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
                        ${deletable ? html`
                            <button onClick=${() => onRestore(entry)}
                                class="px-4 py-2 text-sm font-medium bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition">
                                Restore deleted ${esc(entry.entity_type)}
                            </button>
                        ` : ''}
                        <button onClick=${onClose}
                            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

export function AuditTable({ data, pageSignal, onLoad }) {
    const [pendingDelete, setPendingDelete] = useState(null);
    const [detail, setDetail] = useState(null);

    if (!data || !data.entries || !data.entries.length) {
        const filtered = auditAction.value || auditEntity.value;
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

    async function confirmDelete() {
        if (!pendingDelete) return;
        await deleteAuditEntry(pendingDelete.id);
        onLoad();
    }

    async function confirmRestore(e) {
        await restoreAuditEntry(e.id);
        onLoad();
    }

    return html`
        <div>
            <div class="flex items-center justify-between gap-3 mb-3">
                <${AuditFilters} onLoad=${onLoad} />
            </div>
            <table class="w-full text-xs">
                <thead>
                    <tr class="border-b border-gray-100 dark:border-gray-700/60">
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">#</th>
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Entity</th>
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Name</th>
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Action</th>
                        <th class="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Details</th>
                        <th class="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Time</th>
                        <th class="w-8"></th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100 dark:divide-gray-700/60">
                    ${data.entries.map((e, idx) => {
                        const rowNum = data.total - (data.page - 1) * data.per_page - idx;
                        const as = ACTION_STYLES[e.action] || '';
                        const isDeleted = e.action === 'deleted';
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
                                <td class="py-2 px-1">
                                    <div class="flex items-center gap-0.5">
                                        ${isDeleted ? html`
                                            <button onClick=${(ev) => { ev.stopPropagation(); confirmRestore(e); }}
                                                class="p-1 rounded text-gray-400 hover:text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-500/10 transition"
                                                title="Restore deleted ${esc(e.entity_type)}">
                                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.204a8.25 8.25 0 0113.803-3.7l3.181 3.182"/></svg>
                                            </button>
                                        ` : ''}
                                        <button onClick=${(ev) => { ev.stopPropagation(); setPendingDelete({ id: e.id, name: e.name }); }}
                                            class="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition"
                                            title="Delete entry">
                                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `;
                    })}
                </tbody>
            </table>
            <${Pagination} data=${data} pageSignal=${pageSignal} onLoad=${onLoad} />
            <${ConfirmModal} isOpen=${!!pendingDelete} onClose=${() => setPendingDelete(null)}
                onConfirm=${confirmDelete}
                title="Delete audit entry"
                message=${html`This will permanently delete the audit entry for <span class="font-medium text-gray-700 dark:text-gray-200">${esc(pendingDelete ? pendingDelete.name : '')}</span>. This action cannot be undone.`} />
            <${AuditDetailModal} entry=${detail} onClose=${() => setDetail(null)} onRestore=${async (e) => { setDetail(null); await confirmRestore(e); }} />
        </div>
    `;
}

export function AuditFilters({ onLoad }) {
    return html`
        <div class="flex items-center gap-2">
            <select value=${auditAction.value}
                onChange=${(ev) => { auditAction.value = ev.target.value; auditPage.value = 1; onLoad(); }}
                class="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300">
                <option value="">All actions</option>
                <option value="created">Created</option>
                <option value="updated">Updated</option>
                <option value="deleted">Deleted</option>
                <option value="reordered">Reordered</option>
                <option value="restored">Restored</option>
            </select>
            <select value=${auditEntity.value}
                onChange=${(ev) => { auditEntity.value = ev.target.value; auditPage.value = 1; onLoad(); }}
                class="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700/60 rounded-lg px-2 py-1.5 text-gray-700 dark:text-gray-300">
                <option value="">All entities</option>
                <option value="profile">Profiles</option>
                <option value="workflow">Workflows</option>
            </select>
        </div>
    `;
}
