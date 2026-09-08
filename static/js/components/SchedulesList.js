import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';
import { formatDateTime, formatRelative, colorizeStatus } from '../utils.js';
import { schedules } from '../state.js';
import { toggleSchedule, deleteSchedule, runScheduleNow, loadSchedules } from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';

const CLOCK_ICON = html`<svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;

export function SchedulesList({ onEdit }) {
    const [pendingDelete, setPendingDelete] = useState(null);
    const [busyId, setBusyId] = useState(null);
    const list = schedules.value;

    async function handleToggle(id) {
        await toggleSchedule(id);
        await loadSchedules();
    }

    async function handleRunNow(schedule) {
        setBusyId(schedule.id);
        try {
            await runScheduleNow(schedule.id);
        } finally {
            setBusyId(null);
            await loadSchedules();
        }
    }

    async function handleConfirmDelete() {
        if (!pendingDelete) return;
        await deleteSchedule(pendingDelete.id);
        setPendingDelete(null);
        await loadSchedules();
    }

    if (!list.length) {
        return html`
            <div class="text-center py-16 text-gray-500 dark:text-gray-400">
                <div class="text-4xl mb-3">⏰</div>
                <p class="font-medium">No schedules yet.</p>
                <p class="text-sm mt-1">Create one to run a profile or workflow automatically — like "every hour" or "weekdays at 08:00".</p>
            </div>
        `;
    }

    return html`
        <div class="flex flex-col gap-3">
            ${list.map(s => {
                const missing = !s.target_name;
                const trashed = s.target_trashed;
                const blocked = missing || trashed;
                const sc = colorizeStatus(s.last_status);
                return html`
                    <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl p-4 border border-gray-200 dark:border-gray-700/60 hover:border-gray-300 dark:hover:border-gray-600 transition">
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <div class="flex flex-wrap items-center gap-2">
                                    <span class="w-2 h-2 rounded-full shrink-0 ${s.enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}"
                                        title=${s.enabled ? 'Enabled' : 'Disabled'}></span>
                                    <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
                                        ${s.name || s.target_name || 'Schedule'}
                                    </h3>
                                    <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-violet-500/10 text-violet-600 dark:text-violet-400">
                                        ${s.target_type === 'workflow' ? 'Workflow' : 'Profile'}
                                    </span>
                                    ${blocked ? html`
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20" title=${trashed ? 'Target is in the trash' : 'Target no longer exists'}>
                                            ${trashed ? 'Target in trash' : 'Target missing'}
                                        </span>
                                    ` : ''}
                                </div>
                                <div class="flex flex-wrap items-center gap-1.5 mt-2">
                                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400">
                                        ${CLOCK_ICON}
                                        ${s.description || s.cron}
                                    </span>
                                    <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">${s.cron}</span>
                                </div>
                                <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-xs text-gray-500 dark:text-gray-400">
                                    <span>
                                        <span class="text-gray-400 dark:text-gray-500">Next:</span>
                                        ${blocked || !s.enabled ? html`<span class="text-gray-400 dark:text-gray-500">—</span>`
                                            : s.next_run_at ? html`<span class="text-gray-700 dark:text-gray-300 font-medium">${formatDateTime(s.next_run_at)}</span> <span>(${formatRelative(s.next_run_at)})</span>`
                                            : html`<span class="text-gray-400 dark:text-gray-500">none</span>`}
                                    </span>
                                    <span>
                                        <span class="text-gray-400 dark:text-gray-500">Last:</span>
                                        ${s.last_run_at ? html`<span class=${`font-medium ${sc}`}>${s.last_status || 'running'}</span> <span>${formatDateTime(s.last_run_at)}</span>`
                                            : html`<span class="text-gray-400 dark:text-gray-500">never</span>`}
                                    </span>
                                </div>
                            </div>
                            <div class="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                                <label class="inline-flex items-center cursor-pointer mr-1" title=${s.enabled ? 'Disable schedule' : 'Enable schedule'}>
                                    <input type="checkbox" checked=${s.enabled}
                                        onChange=${() => handleToggle(s.id)}
                                        class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0 cursor-pointer" />
                                    <span class="ml-1.5 text-xs text-gray-500 dark:text-gray-400">${s.enabled ? 'On' : 'Off'}</span>
                                </label>
                                <button onClick=${() => handleRunNow(s)} disabled=${busyId === s.id}
                                    title="Run now (does not change the schedule)"
                                    class="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20 disabled:opacity-50 text-xs font-medium rounded-lg transition">
                                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Run now
                                </button>
                                <button onClick=${() => onEdit && onEdit(s)}
                                    class="px-2.5 py-1.5 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 transition">Edit</button>
                                <button onClick=${() => setPendingDelete(s)} title="Delete" aria-label="Delete"
                                    class="inline-flex items-center justify-center p-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">
                                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            })}
        </div>
        <${ConfirmModal}
            isOpen=${!!pendingDelete}
            onClose=${() => setPendingDelete(null)}
            onConfirm=${handleConfirmDelete}
            title="Delete schedule"
            message=${html`This will stop automatic runs for <span class="font-medium text-gray-700 dark:text-gray-200">${pendingDelete ? (pendingDelete.name || pendingDelete.cron) : ''}</span>. The profile or workflow itself is not affected.`}
        />
    `;
}
