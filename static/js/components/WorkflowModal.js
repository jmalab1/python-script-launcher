import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';
import { profiles } from '../state.js';
import { saveWorkflow, loadWorkflows } from '../api.js';

export function WorkflowModal({ isOpen, onClose, workflow }) {
    const [name, setName] = useState('');
    const [continueOnError, setContinueOnError] = useState(false);
    const [localSteps, setLocalSteps] = useState([]);
    const [openArgs, setOpenArgs] = useState(null);
    const [editingId, setEditingId] = useState(null);

    useEffect(() => {
        if (isOpen) {
            if (workflow) {
                setEditingId(workflow.id);
                setName(workflow.name || '');
                setContinueOnError(!!workflow.continue_on_error);
                const normalized = (workflow.steps || []).map(s => s.type === 'parallel'
                    ? { ...s, profiles: (s.profiles || []).map(p => ({ ...p, _argsText: (p.args || []).join('\n') })) }
                    : { ...s, _argsText: (s.args || []).join('\n') });
                setLocalSteps(JSON.parse(JSON.stringify(normalized)));
            } else {
                setEditingId(null);
                setName('');
                setContinueOnError(false);
                setLocalSteps([]);
            }
            setOpenArgs(null);
        }
    }, [isOpen, workflow]);

    function addSequentialStep() {
        setLocalSteps([...localSteps, { type: 'sequential', profile_id: profiles.value[0]?.id || '', args: [], _argsText: '' }]);
    }

    function addParallelGroup() {
        setLocalSteps([...localSteps, { type: 'parallel', profiles: [] }]);
    }

    function addProfileToParallelGroup(groupIdx) {
        setLocalSteps(localSteps.map((s, i) => {
            if (i !== groupIdx || s.type !== 'parallel') return s;
            return { ...s, profiles: [...s.profiles, { profile_id: profiles.value[0]?.id || '', args: [], _argsText: '' }] };
        }));
    }

    function toggleArgs(key) {
        setOpenArgs(openArgs === key ? null : key);
    }

    function updateStepArgsText(idx, text) {
        setLocalSteps(localSteps.map((s, i) => i === idx ? { ...s, _argsText: text } : s));
    }

    function updateGroupProfileArgsText(groupIdx, profileIdx, text) {
        setLocalSteps(localSteps.map((s, i) => {
            if (i !== groupIdx || s.type !== 'parallel') return s;
            return { ...s, profiles: s.profiles.map((p, pi) => pi === profileIdx ? { ...p, _argsText: text } : p) };
        }));
    }

    function parseArgsText(text, fallback) {
        const src = (text !== undefined && text !== null) ? text : (fallback || []).join('\n');
        return src.split('\n').map(t => t.trim()).filter(Boolean);
    }

    function updateStepArgValue(idx, name, val) {
        setLocalSteps(localSteps.map((s, i) => {
            if (i !== idx) return s;
            return { ...s, arg_values: { ...(s.arg_values || {}), [name]: val } };
        }));
    }

    function updateGroupProfileArgValue(groupIdx, profileIdx, name, val) {
        setLocalSteps(localSteps.map((s, i) => {
            if (i !== groupIdx || s.type !== 'parallel') return s;
            return { ...s, profiles: s.profiles.map((p, pi) => pi === profileIdx ? { ...p, arg_values: { ...(p.arg_values || {}), [name]: val } } : p) };
        }));
    }

    function customFieldsFor(entry, onSet) {
        const prof = profileMap[entry.profile_id];
        const cas = (prof && prof.custom_args) || [];
        if (!cas.length) return null;
        return html`
            <div class="flex flex-wrap items-center gap-3">
                ${cas.map(ca => {
                    const eff = (entry.arg_values && entry.arg_values[ca.name] !== undefined)
                        ? entry.arg_values[ca.name]
                        : (ca.value !== undefined ? ca.value : (ca.default || ''));
                    if (ca.type === 'checkbox') {
                        return html`
                            <label class="inline-flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-300 cursor-pointer">
                                <input type="checkbox" checked=${eff === 'true'}
                                    onChange=${e => onSet(ca.name, e.target.checked ? 'true' : 'false')}
                                    class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0" />
                                ${esc(ca.label || ca.name)}
                            </label>`;
                    }
                    return html`
                        <div class="flex items-center gap-1.5">
                            <label class="text-[11px] text-gray-500 dark:text-gray-400 whitespace-nowrap">${esc(ca.label || ca.name)}</label>
                            <input type="text" value=${eff}
                                onInput=${e => onSet(ca.name, e.target.value)}
                                placeholder=${esc(ca.name)}
                                class="w-28 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                        </div>`;
                })}
            </div>`;
    }

    function removeProfileFromParallelGroup(groupIdx, profileIdx) {
        setOpenArgs(null);
        const updated = localSteps.map((s, i) => {
            if (i !== groupIdx || s.type !== 'parallel') return s;
            return { ...s, profiles: s.profiles.filter((_, pi) => pi !== profileIdx) };
        }).filter(s => !(s.type === 'parallel' && s.profiles.length === 0));
        setLocalSteps(updated);
    }

    function updateGroupProfile(groupIdx, profileIdx, pid) {
        setLocalSteps(localSteps.map((s, i) => {
            if (i !== groupIdx || s.type !== 'parallel') return s;
            return { ...s, profiles: s.profiles.map((p, pi) => pi === profileIdx ? { ...p, profile_id: pid } : p) };
        }));
    }

    function updateSequentialProfile(idx, pid) {
        setLocalSteps(localSteps.map((s, i) => i === idx ? { ...s, profile_id: pid } : s));
    }

    function removeStep(idx) {
        setOpenArgs(null);
        setLocalSteps(localSteps.filter((_, i) => i !== idx));
    }

    function moveStep(idx, dir) {
        setOpenArgs(null);
        const j = idx + dir;
        const updated = [...localSteps];
        [updated[idx], updated[j]] = [updated[j], updated[idx]];
        setLocalSteps(updated);
    }

    async function handleSave() {
        const trimmedName = name.trim();
        if (!trimmedName) { alert('Name is required.'); return; }
        if (!localSteps.length) { alert('Add at least one step.'); return; }
        const missingProfile = localSteps.some(s => s.type === 'parallel'
            ? !(s.profiles || []).length || s.profiles.some(p => !p.profile_id)
            : !s.profile_id);
        if (missingProfile) { alert('Every step needs a selected profile.'); return; }
        const stepsToSave = localSteps.map(s => s.type === 'parallel'
            ? { type: 'parallel', profiles: (s.profiles || []).map(p => ({ profile_id: p.profile_id, args: parseArgsText(p._argsText, p.args), arg_values: p.arg_values || {} })) }
            : { type: 'sequential', profile_id: s.profile_id, args: parseArgsText(s._argsText, s.args), arg_values: s.arg_values || {} });
        await saveWorkflow({
            id: editingId, name: trimmedName, steps: stepsToSave,
            extra_args: [], continue_on_error: continueOnError,
        });
        await loadWorkflows();
        onClose();
    }

    if (!isOpen) return null;

    const profileList = profiles.value;
    const profileMap = Object.fromEntries(profileList.map(p => [p.id, p]));

    const upBtn = (i) => html`<button onClick=${() => moveStep(i, -1)} class="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5"/></svg></button>`;
    const downBtn = (i) => html`<button onClick=${() => moveStep(i, 1)} class="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5"/></svg></button>`;
    const xBtn = (fn) => html`<button onClick=${fn} class="p-1 text-gray-400 hover:text-red-500 transition"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg></button>`;

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-y-auto border border-gray-200 dark:border-gray-700/60">
                    <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-t-2xl z-10">
                        <div class="flex items-center justify-between">
                            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">
                                ${editingId ? 'Edit Workflow' : 'New Workflow'}
                            </h2>
                            <button onClick=${onClose} class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="px-6 py-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Workflow Name</label>
                            <input type="text" value=${name} onInput=${e => setName(e.target.value)}
                                placeholder="e.g. ETL Pipeline"
                                class="w-full bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Steps</label>
                            <div class="flex gap-2 mb-3">
                                <button onClick=${addSequentialStep}
                                    disabled=${!profileList.length}
                                    class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed">+ Add Step</button>
                                <button onClick=${addParallelGroup}
                                    disabled=${!profileList.length}
                                    class="bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 text-sm font-medium px-3 py-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed">+ Parallel Group</button>
                            </div>
                            <div class="space-y-2">
                                ${!localSteps.length ? html`<div class="text-xs text-gray-400 py-2">${profileList.length ? 'No steps added yet. Use "+ Add Step" for a single step, or "+ Parallel Group" to run multiple profiles at once.' : 'Create a profile first, then add it as a step here.'}</div>` : localSteps.map((s, i) => {
                                    if (s.type === 'parallel') {
                                        const groupProfiles = s.profiles || [];
                                        return html`
                                            <div class="border-2 border-green-200 dark:border-green-500/30 rounded-xl p-3 bg-green-50/30 dark:bg-green-500/5">
                                                <div class="flex items-center justify-between mb-2">
                                                    <div class="flex items-center gap-2">
                                                        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/30">PARALLEL</span>
                                                        <span class="text-xs text-gray-500 dark:text-gray-400">${groupProfiles.length} profile${groupProfiles.length !== 1 ? 's' : ''} run at the same time</span>
                                                    </div>
                                                    <div class="flex items-center gap-0.5 shrink-0">
                                                        ${i > 0 ? upBtn(i) : ''}
                                                        ${i < localSteps.length - 1 ? downBtn(i) : ''}
                                                        ${xBtn(() => removeStep(i))}
                                                    </div>
                                                </div>
                                                <div class="space-y-1.5 ml-1">
                                                    ${groupProfiles.map((p, pi) => html`
                                                        <div>
                                                            <div class="flex items-center gap-2 p-1.5 bg-white dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/60 rounded-lg">
                                                                <div class="w-5 h-5 rounded-full bg-green-500/10 text-green-600 dark:text-green-400 flex items-center justify-center text-[10px] font-bold shrink-0">${pi + 1}</div>
                                                                <select onChange=${e => updateGroupProfile(i, pi, e.target.value)}
                                                                    class="flex-1 min-w-0 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition">
                                                                    ${!p.profile_id ? html`<option value="" selected disabled>Select profile...</option>` : ''}
                                                                    ${profileList.map(pl => html`<option value=${pl.id} selected=${p.profile_id === pl.id}>${esc(pl.name)}</option>`)}
                                                                </select>
                                                                <button onClick=${() => toggleArgs(`p${i}-${pi}`)}
                                                                    title="Extra arguments for this profile"
                                                                    class="shrink-0 inline-flex items-center gap-1 px-1.5 py-1 text-[11px] font-medium rounded border transition ${(p._argsText || '').trim() ? 'border-violet-200 dark:border-violet-500/30 text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10' : 'border-gray-200 dark:border-gray-700/60 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50'} ${openArgs === `p${i}-${pi}` ? 'bg-gray-100 dark:bg-gray-700/50' : ''}">
                                                                    Args${(p._argsText || '').trim() ? html`<span class="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold bg-violet-500 text-white">${parseArgsText(p._argsText).length}</span>` : ''}
                                                                </button>
                                                                ${xBtn(() => removeProfileFromParallelGroup(i, pi))}
                                                            </div>
                                                            ${openArgs === `p${i}-${pi}` ? html`
                                                                <div class="px-1.5 pt-1 pb-1.5 space-y-2">
                                                                    ${customFieldsFor(p, (name, val) => updateGroupProfileArgValue(i, pi, name, val))}
                                                                    <textarea rows="2" value=${p._argsText || ''} onInput=${e => updateGroupProfileArgsText(i, pi, e.target.value)}
                                                                        placeholder="Extra arguments, one per line"
                                                                        class="w-full bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-2.5 py-2 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 font-mono focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition resize-y"></textarea>
                                                                </div>
                                                            ` : ''}
                                                        </div>
                                                    `)}
                                                    <button onClick=${() => addProfileToParallelGroup(i)} class="w-full text-left text-xs text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300 py-1 px-2 rounded transition">+ Add Profile</button>
                                                </div>
                                            </div>`;
                                    }
                                    return html`
                                        <div>
                                            <div class="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700/60 rounded-lg">
                                                <div class="w-6 h-6 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center justify-center text-xs font-bold shrink-0">${i + 1}</div>
                                                <select onChange=${e => updateSequentialProfile(i, e.target.value)}
                                                    class="flex-1 min-w-0 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition">
                                                    ${!s.profile_id ? html`<option value="" selected disabled>Select profile...</option>` : ''}
                                                    ${profileList.map(pl => html`<option value=${pl.id} selected=${s.profile_id === pl.id}>${esc(pl.name)} — ${esc(pl.script_path)}</option>`)}
                                                </select>
                                                <button onClick=${() => toggleArgs(`s${i}`)}
                                                    title="Extra arguments for this step"
                                                    class="shrink-0 inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded border transition ${(s._argsText || '').trim() ? 'border-violet-200 dark:border-violet-500/30 text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10' : 'border-gray-200 dark:border-gray-700/60 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50'} ${openArgs === `s${i}` ? 'bg-gray-100 dark:bg-gray-700/50' : ''}">
                                                    Args${(s._argsText || '').trim() ? html`<span class="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold bg-violet-500 text-white">${parseArgsText(s._argsText).length}</span>` : ''}
                                                </button>
                                                <div class="flex items-center gap-0.5 shrink-0">
                                                    ${i > 0 ? upBtn(i) : ''}
                                                    ${i < localSteps.length - 1 ? downBtn(i) : ''}
                                                    ${xBtn(() => removeStep(i))}
                                                </div>
                                            </div>
                                            ${openArgs === `s${i}` ? html`
                                                <div class="px-2 pt-1.5 pb-2 space-y-2">
                                                    ${customFieldsFor(s, (name, val) => updateStepArgValue(i, name, val))}
                                                    <textarea rows="2" value=${s._argsText || ''} onInput=${e => updateStepArgsText(i, e.target.value)}
                                                        placeholder="Extra arguments for this step, one per line"
                                                        class="w-full bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-2.5 py-2 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 font-mono focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition resize-y"></textarea>
                                                </div>
                                            ` : ''}
                                        </div>`;
                                })}
                            </div>
                        </div>
                        <div class="flex items-center gap-3">
                            <input type="checkbox" checked=${continueOnError}
                                onChange=${e => setContinueOnError(e.target.checked)}
                                class="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0" />
                            <label class="text-sm text-gray-700 dark:text-gray-300">Continue on error</label>
                        </div>
                    </div>
                    <div class="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-b-2xl flex justify-end gap-2">
                        <button onClick=${onClose} class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Cancel</button>
                        <button onClick=${handleSave} class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-4 py-2 rounded-lg transition">Save Workflow</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}
