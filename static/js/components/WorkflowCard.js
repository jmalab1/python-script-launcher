import { html, useState } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';
import { profiles, schedules, scriptStatusCache, TRASH_GROUP } from '../state.js';
import { runWorkflow, loadWorkflows, duplicateWorkflow, restoreWorkflow, permanentDeleteWorkflow } from '../api.js';
import { ConfirmModal } from './ConfirmModal.js';

export function WorkflowCard({ workflow, onEdit, onRun }) {
    const w = workflow;
    const steps = w.steps || [];
    const [expanded, setExpanded] = useState(false);
    const [pendingDelete, setPendingDelete] = useState(null);
    const [pendingPermanentDelete, setPendingPermanentDelete] = useState(null);
    const isTrashed = w.group === TRASH_GROUP;
    const hasSchedule = schedules.value.some(s => s.enabled && s.target_type === 'workflow' && s.target_id === w.id);
    const profileMap = Object.fromEntries(profiles.value.map(p => [p.id, p]));
    const profFor = (entry) => entry.profile || profileMap[entry.profile_id] || {};
    const cache = scriptStatusCache.value;

    const totalSteps = steps.reduce((n, s) => n + (s.type === 'parallel' ? (s.profiles || []).length : 1), 0);

    function collectMissing() {
        const missing = [];
        for (const s of steps) {
            if (s.type === 'parallel') {
                for (const p of (s.profiles || [])) {
                    const prof = profFor(p);
                    if (cache[prof.script_path] === false) missing.push(prof.name || p.profile_id);
                }
            } else {
                const prof = profFor(s);
                if (cache[prof.script_path] === false) missing.push(prof.name || s.profile_id);
            }
        }
        return missing;
    }

    const missing = collectMissing();
    const hasMissingScripts = missing.length > 0;

    async function handleRun() {
        if (hasMissingScripts) {
            if (!confirm(`These profiles have missing scripts: ${missing.join(', ')}\n\nRun anyway?`)) return;
        }
        const res = await runWorkflow(w.id);
        if (res.run_id && onRun) onRun(res.run_id, 'Workflow Run');
    }

    function confirmDelete() {
        setPendingDelete(w);
    }

    async function handleConfirmDelete() {
        const { deleteWorkflow } = await import('../api.js');
        await deleteWorkflow(w.id);
        await loadWorkflows();
    }

    async function handleRestore() {
        await restoreWorkflow(w.id);
        await loadWorkflows();
    }

    async function handleConfirmPermanentDelete() {
        await permanentDeleteWorkflow(w.id);
        await loadWorkflows();
    }

    async function handleDuplicate() {
        await duplicateWorkflow(w.id);
        await loadWorkflows();
    }

    function effectiveArgs(entry, prof) {
        const overrides = (entry && entry.arg_values) || {};
        const built = [];
        for (const ca of (prof.custom_args || [])) {
            const flag = ca.name || '';
            if (!flag) continue;
            const val = overrides[flag] !== undefined ? overrides[flag] : (ca.value !== undefined ? ca.value : (ca.default || ''));
            if (ca.type === 'checkbox') {
                if (val === 'true') built.push(flag);
            } else if (val) {
                built.push(flag, String(val));
            }
        }
        return [...built, ...((entry && entry.args) || [])];
    }

    function argsSnippet(stepArgs) {
        if (!stepArgs.length) return '';
        return html`<span class="text-violet-600 dark:text-violet-400"> ${esc(stepArgs.join(' '))}</span>`;
    }

    function renderStep(s, i) {
        const isLast = i === steps.length - 1;

        if (s.type === 'parallel') {
            const groupProfiles = s.profiles || [];
            return html`
                <div class="flex items-start gap-3 ${!isLast ? 'pb-3' : ''}">
                    <div class="flex flex-col items-center shrink-0 pt-0.5">
                        <span class="flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-500/30">P</span>
                        ${!isLast ? html`<div class="w-px h-full min-h-[8px] bg-gray-200 dark:bg-gray-700 mt-1"></div>` : ''}
                    </div>
                    <div class="min-w-0 flex-1 border-2 border-green-200 dark:border-green-500/30 rounded-lg p-2 bg-green-50/30 dark:bg-green-500/5">
                        <div class="flex items-center gap-1.5 mb-1">
                            <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/30">PARALLEL</span>
                            <span class="text-[10px] text-gray-400">${groupProfiles.length} profile${groupProfiles.length !== 1 ? 's' : ''}</span>
                        </div>
                        ${groupProfiles.map((p, pi) => {
                            const prof = profFor(p);
                            const stepMissing = cache[prof.script_path] === false;
                            const stepArgs = effectiveArgs(p, prof);
                            return html`
                                <div class="flex items-start gap-2 py-0.5 ${pi < groupProfiles.length - 1 ? 'border-b border-green-100 dark:border-green-500/10' : ''}">
                                    <span class="text-[10px] font-medium shrink-0 ${stepMissing ? 'text-red-700 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}">${esc(prof.name || 'Unknown')}</span>
                                    <span class="text-[10px] ${stepMissing ? 'text-red-500 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'} flex-1 min-w-0 font-mono break-all">${esc(prof.script_path || '—')}${argsSnippet(stepArgs)}</span>
                                    ${stepMissing ? html`<span class="text-[9px] text-red-500 shrink-0">missing</span>` : ''}
                                </div>`;
                        })}
                    </div>
                </div>`;
        }

        const prof = profFor(s);
        const stepMissing = cache[prof.script_path] === false;
        const stepArgs = effectiveArgs(s, prof);
        return html`
            <div class="flex items-start gap-3 ${!isLast ? 'pb-3' : ''}">
                <div class="flex flex-col items-center shrink-0 pt-0.5">
                    <span class="flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold ${stepMissing ? 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-500/30' : 'bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-500/30'}">${i + 1}</span>
                    ${!isLast ? html`<div class="w-px h-full min-h-[8px] bg-gray-200 dark:bg-gray-700 mt-1"></div>` : ''}
                </div>
                <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-xs font-medium ${stepMissing ? 'text-red-700 dark:text-red-400' : 'text-gray-800 dark:text-gray-200'}">${esc(prof.name || 'Unknown Profile')}</span>
                        ${stepMissing ? html`<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20"><svg class="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>missing</span>` : ''}
                    </div>
                    <div class="text-[11px] ${stepMissing ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'} mt-0.5 font-mono break-all">${esc(prof.script_path || '—')}${argsSnippet(stepArgs)}</div>
                </div>
            </div>`;
    }

    return html`
        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border ${hasMissingScripts ? 'border-amber-200 dark:border-amber-500/30' : 'border-gray-200 dark:border-gray-700/60'} hover:border-gray-300 dark:hover:border-gray-600 transition group">
            <div class="p-4">
                <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-3">
                    <div class="min-w-0 flex-1">
                        <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100">${esc(w.name)}</h3>
                        <div class="flex flex-wrap items-center gap-1.5 mt-1.5">
                            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">${totalSteps} step${totalSteps !== 1 ? 's' : ''}</span>
                            ${hasSchedule ? html`
                                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400" title="Runs automatically on a schedule">
                                    <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                                    Scheduled
                                </span>
                            ` : ''}
                            ${hasMissingScripts ? html`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>Missing script</span>` : ''}
                            ${w.continue_on_error ? html`<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400">continues on error</span>` : ''}
                        </div>
                    </div>
                    <div class="flex items-center gap-1 shrink-0 flex-wrap">
                        ${isTrashed ? html`
                            <button onClick=${handleRestore}
                                class="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-xs font-medium rounded-lg border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20 transition">
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3"/></svg> Restore
                            </button>
                            <button onClick=${() => setPendingPermanentDelete(w)} title="Permanently delete" aria-label="Permanently delete"
                                class="inline-flex items-center justify-center p-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                            </button>
                        ` : html`
                            <button onClick=${handleRun}
                                class="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 text-xs font-medium rounded-lg border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20 transition">
                                <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Run
                            </button>
                            <button onClick=${() => onEdit && onEdit(w)}
                                class="px-2.5 py-1.5 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 transition">Edit</button>
                            <button onClick=${handleDuplicate} title="Duplicate workflow"
                                class="px-2.5 py-1.5 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 transition">Copy</button>
                            <button onClick=${confirmDelete} title="Delete" aria-label="Delete"
                                class="inline-flex items-center justify-center p-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                            </button>
                        `}
                    </div>
                </div>
                ${steps.length ? html`
                <div class="border-t border-gray-100 dark:border-gray-700/60 pt-3 group/steps">
                    <div class="flex items-center justify-between cursor-pointer select-none" onClick=${() => setExpanded(e => !e)} title=${expanded ? 'Collapse steps' : 'Expand steps'}>
                        <span class="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Steps</span>
                        <span class="flex items-center gap-1 text-[11px] text-gray-400 dark:text-gray-500">
                            ${!expanded && html`<span class="group-hover/steps:hidden">hover to view</span><span class="hidden group-hover/steps:inline">Click to keep expanded</span>`}
                            ${expanded && html`<span class="group-hover/steps:hidden">expanded</span><span class="hidden group-hover/steps:inline">Click to collapse</span>`}
                            <svg class="w-3 h-3 transition-transform duration-200 ${expanded ? 'rotate-180' : 'group-hover/steps:rotate-180'}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
                        </span>
                    </div>
                    <div class="grid grid-rows-[0fr] transition-[grid-template-rows] duration-200 ${expanded ? 'grid-rows-[1fr]' : 'group-hover/steps:grid-rows-[1fr]'}">
                        <div class="overflow-hidden">
                            <div class="space-y-0 pt-2">
                                ${steps.map((s, i) => renderStep(s, i))}
                            </div>
                        </div>
                    </div>
                </div>` : ''}
            </div>
        </div>
        <${ConfirmModal}
            isOpen=${!!pendingDelete}
            onClose=${() => setPendingDelete(null)}
            onConfirm=${handleConfirmDelete}
            title="Delete workflow"
            message=${html`This will move <span class="font-medium text-gray-700 dark:text-gray-200">${esc(w.name)}</span> to the trash.`}
        />
        <${ConfirmModal}
            isOpen=${!!pendingPermanentDelete}
            onClose=${() => setPendingPermanentDelete(null)}
            onConfirm=${handleConfirmPermanentDelete}
            title="Permanently delete workflow"
            message=${html`This will permanently delete <span class="font-medium text-gray-700 dark:text-gray-200">${esc(w.name)}</span>. This action cannot be undone.`}
        />
    `;
}
