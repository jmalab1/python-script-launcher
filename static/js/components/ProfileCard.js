import { html, useState } from '../../vendor/standalone-preact.esm.js';
import { scriptStatusCache, schedules, tags, TRASH_GROUP } from '../state.js';
import { tagColor } from '../tagColors.js';
import { runProfile, saveProfile as apiSaveProfile, loadProfiles, duplicateProfile, restoreProfile, permanentDeleteProfile } from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';
import { ErrorBanner } from './ErrorBanner.js';

export function ProfileCard({ profile, onEdit, onRun }) {
    const p = profile;
    const cache = scriptStatusCache.value;
    const scriptMissing = cache[p.script_path] === false;
    const ca = p.custom_args || [];
    const sa = p.args || [];
    const [pendingDelete, setPendingDelete] = useState(null);
    const [pendingPermanentDelete, setPendingPermanentDelete] = useState(null);
    const [error, setError] = useState('');
    const isTrashed = p.group === TRASH_GROUP;
    const hasSchedule = schedules.value.some(s => s.enabled && s.target_type === 'profile' && s.target_id === p.id);
    const itemTags = (p.tags || [])
        .map(id => tags.value.find(t => t.id === id))
        .filter(Boolean);

    async function handleRun() {
        if (scriptMissing) return;
        setError('');
        const argValues = {};
        if (p.custom_args) p.custom_args.forEach((ca, i) => {
            const el = document.getElementById(`arg-${p.id}-${i}`);
            if (el) argValues[ca.name] = ca.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value;
        });
        try {
            const res = await runProfile(p.id, argValues);
            if (res.error) { setError(res.error); return; }
            if (res.run_id && onRun) onRun(res.run_id, 'Profile Run');
        } catch (err) {
            setError(err.message || 'Could not start the run.');
        }
    }

    function confirmDelete() {
        setPendingDelete(p);
    }

    async function handleConfirmDelete() {
        const { deleteProfile } = await import('../api.js');
        await deleteProfile(p.id);
        await loadProfiles();
    }

    async function handleRestore() {
        await restoreProfile(p.id);
        await loadProfiles();
    }

    async function handleConfirmPermanentDelete() {
        await permanentDeleteProfile(p.id);
        await loadProfiles();
    }

    async function handleDuplicate() {
        await duplicateProfile(p.id);
        await loadProfiles();
    }

    function handleArgChange(el) {
        const idx = parseInt(el.dataset.idx);
        const ca = p.custom_args[idx];
        if (!ca) return;
        ca.value = ca.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value;
        apiSaveProfile(p);
    }

    const scriptBadge = scriptMissing
        ? html`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20" title="Script not found">
            <svg class="w-3 h-3 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
            ${p.script_path}
        </span>`
        : html`<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">${p.script_path}</span>`;

    return html`
        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl p-4 border ${scriptMissing ? 'border-red-200 dark:border-red-500/30' : 'border-gray-200 dark:border-gray-700/60'} hover:border-gray-300 dark:hover:border-gray-600 transition group">
            <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div class="min-w-0 flex-1">
                    <div class="flex items-center flex-wrap gap-x-1.5 gap-y-1">
                        <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100">${p.name}</h3>
                        ${itemTags.map(t => html`
                            <span class="inline-flex items-center gap-0.5 px-1 py-px rounded-sm text-[9px] font-medium border ${tagColor(t).chip}">
                                <svg class="w-1.5 h-1.5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/></svg>
                                ${t.name}
                            </span>
                        `)}
                    </div>
                    <div class="flex flex-wrap items-center gap-1.5 mt-2">
                        ${scriptBadge}
                        ${hasSchedule ? html`
                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400" title="Runs automatically on a schedule">
                                <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                                Scheduled
                            </span>
                        ` : ''}
                        ${sa.map(a => html`<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400">${a}</span>`)}
                    </div>
                    ${ca.length ? html`
                        <div class="flex flex-wrap items-center gap-3 mt-3">
                            ${ca.map((c, i) => {
                                if (c.type === 'checkbox') return html`
                                    <label class="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300 cursor-pointer">
                                        <input type="checkbox" id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                            checked=${c.value === 'true'}
                                            onChange=${(e) => handleArgChange(e.target)}
                                            class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0" />
                                        ${c.label || c.name}
                                    </label>`;
                                if (c.type === 'date') return html`
                                    <div class="flex items-center gap-1.5">
                                        <label class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">${c.label || c.name}</label>
                                        <input type="date" id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                            value=${c.value || c.default || ''}
                                            onChange=${(e) => handleArgChange(e.target)}
                                            class="w-36 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                    </div>`;
                                if (c.type === 'enum') {
                                    const cur = c.value || c.default || '';
                                    const opts = String(c.options || '').split(',').map(s => s.trim()).filter(Boolean);
                                    return html`
                                        <div class="flex items-center gap-1.5">
                                            <label class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">${c.label || c.name}</label>
                                            <select id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                                onChange=${(e) => handleArgChange(e.target)}
                                                class="max-w-[14rem] bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition">
                                                <option value="" selected=${cur === ''}>-- select --</option>
                                                ${opts.map(opt => html`<option value=${opt} selected=${cur === opt}>${opt}</option>`)}
                                            </select>
                                        </div>`;
                                }
                                return html`
                                    <div class="flex items-center gap-1.5">
                                        <label class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">${c.label || c.name}</label>
                                        <input type="text" id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                            value=${c.value || c.default || ''}
                                            onChange=${(e) => handleArgChange(e.target)}
                                            placeholder=${c.name}
                                            class="w-32 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                    </div>`;
                            })}
                        </div>
                    ` : ''}
                    <${ErrorBanner} message=${error} />
                </div>
                <div class="flex items-center gap-1 shrink-0 flex-wrap">
                    ${isTrashed ? html`
                        <button onClick=${handleRestore}
                            class="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20 text-xs font-medium rounded-lg transition">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3"/></svg> Restore
                        </button>
                        <button onClick=${() => setPendingPermanentDelete(p)} title="Permanently delete" aria-label="Permanently delete"
                            class="inline-flex items-center justify-center p-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                        </button>
                    ` : html`
                        <button onClick=${handleRun} disabled=${scriptMissing}
                            title=${scriptMissing ? 'Script not found' : ''}
                            class="inline-flex items-center gap-1 px-2.5 py-1.5 ${scriptMissing
                                ? 'bg-gray-100 dark:bg-gray-700/50 text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-700/60 cursor-not-allowed'
                                : 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20'} text-xs font-medium rounded-lg transition">
                            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Run
                        </button>
                        <button onClick=${() => onEdit && onEdit(p)} title="Edit profile"
                            class="inline-flex items-center justify-center p-1.5 bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-400 rounded-lg border border-violet-200 dark:border-violet-500/20 hover:bg-violet-100 dark:hover:bg-violet-500/20 transition">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></svg>
                        </button>
                        <button onClick=${handleDuplicate} title="Duplicate profile"
                            class="inline-flex items-center justify-center p-1.5 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 rounded-lg border border-blue-200 dark:border-blue-500/20 hover:bg-blue-100 dark:hover:bg-blue-500/20 transition">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H9.75"/></svg>
                        </button>
                        <button onClick=${confirmDelete} title="Delete" aria-label="Delete"
                            class="inline-flex items-center justify-center p-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                        </button>
                    `}
                </div>
            </div>
        </div>
        <${ConfirmModal}
            isOpen=${!!pendingDelete}
            onClose=${() => setPendingDelete(null)}
            onConfirm=${handleConfirmDelete}
            title="Delete profile"
            message=${html`This will move <span class="font-medium text-gray-700 dark:text-gray-200">${p.name}</span> to the trash.`}
        />
        <${ConfirmModal}
            isOpen=${!!pendingPermanentDelete}
            onClose=${() => setPendingPermanentDelete(null)}
            onConfirm=${handleConfirmPermanentDelete}
            title="Permanently delete profile"
            message=${html`This will permanently delete <span class="font-medium text-gray-700 dark:text-gray-200">${p.name}</span>. This action cannot be undone.`}
        />
    `;
}
