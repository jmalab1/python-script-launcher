import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';
import { profiles, workflows } from '../state.js';
import { saveSchedule, loadSchedules, previewCron } from '../api.js';

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const UNIT_MAX = { minutes: 59, hours: 23, days: 31 };

export function ScheduleModal({ isOpen, onClose, schedule }) {
    const [editingId, setEditingId] = useState(null);
    const [name, setName] = useState('');
    const [targetType, setTargetType] = useState('profile');
    const [targetId, setTargetId] = useState('');
    const [mode, setMode] = useState('preset');
    const [presetKind, setPresetKind] = useState('repeat');
    const [repeatN, setRepeatN] = useState(30);
    const [repeatUnit, setRepeatUnit] = useState('minutes');
    const [repeatDaysTime, setRepeatDaysTime] = useState('00:00');
    const [dailyTime, setDailyTime] = useState('09:00');
    const [weeklyDays, setWeeklyDays] = useState([1]);
    const [weeklyTime, setWeeklyTime] = useState('09:00');
    const [monthlyDay, setMonthlyDay] = useState(15);
    const [monthlyTime, setMonthlyTime] = useState('09:00');
    const [cronInput, setCronInput] = useState('');
    const [enabled, setEnabled] = useState(true);
    const [preview, setPreview] = useState(null);
    const [previewError, setPreviewError] = useState('');

    useEffect(() => {
        if (isOpen) {
            if (schedule) {
                setEditingId(schedule.id || null);
                setName(schedule.name || '');
                setTargetType(schedule.target_type || 'profile');
                setTargetId(schedule.target_id || '');
                setCronInput(schedule.cron || '');
                setMode('custom');
                setEnabled(schedule.enabled !== false);
            } else {
                setEditingId(null);
                setName('');
                setTargetType('profile');
                setTargetId('');
                setMode('preset');
                setPresetKind('repeat');
                setRepeatN(30);
                setRepeatUnit('minutes');
                setRepeatDaysTime('00:00');
                setDailyTime('09:00');
                setWeeklyDays([1]);
                setWeeklyTime('09:00');
                setMonthlyDay(15);
                setMonthlyTime('09:00');
                setCronInput('');
                setEnabled(true);
            }
            setPreview(null);
            setPreviewError('');
        }
    }, [isOpen, schedule]);

    function clampN(raw, unit) {
        return Math.max(1, Math.min(UNIT_MAX[unit], parseInt(raw, 10) || 1));
    }

    function splitTime(t) {
        const [h, m] = String(t).split(':').map(v => parseInt(v, 10) || 0);
        return [m, h];
    }

    function presetToCron() {
        if (presetKind === 'repeat') {
            const n = clampN(repeatN, repeatUnit);
            if (repeatUnit === 'minutes') return `*/${n} * * * *`;
            if (repeatUnit === 'hours') return `0 */${n} * * *`;
            const [m, h] = splitTime(repeatDaysTime);
            return `${m} ${h} */${n} * *`;
        }
        if (presetKind === 'daily') {
            const [m, h] = splitTime(dailyTime);
            return `${m} ${h} * * *`;
        }
        if (presetKind === 'weekly') {
            const [m, h] = splitTime(weeklyTime);
            const days = weeklyDays.length ? [...weeklyDays].sort((a, b) => a - b).join(',') : '1';
            return `${m} ${h} * * ${days}`;
        }
        const [m, h] = splitTime(monthlyTime);
        return `${m} ${h} ${clampN(monthlyDay, 'days')} * *`;
    }

    function currentCron() {
        return mode === 'custom' ? cronInput : presetToCron();
    }

    useEffect(() => {
        if (!isOpen) { setPreview(null); setPreviewError(''); return; }
        const c = currentCron().trim();
        if (!c) { setPreview(null); setPreviewError(''); return; }
        let alive = true;
        previewCron(c).then(res => {
            if (!alive) return;
            if (res.error) { setPreview(null); setPreviewError(res.error); }
            else { setPreview(res); setPreviewError(''); }
        });
        return () => { alive = false; };
    }, [isOpen, mode, presetKind, repeatN, repeatUnit, repeatDaysTime, dailyTime, weeklyDays, weeklyTime, monthlyDay, monthlyTime, cronInput]);

    function toggleDay(d) {
        setWeeklyDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d]);
    }

    const targetOptions = (targetType === 'workflow' ? workflows.value : profiles.value)
        .filter(item => item.group !== '__trash__');

    async function handleSave() {
        if (!targetId) { alert('Pick a profile or workflow to schedule.'); return; }
        const finalCron = currentCron().trim();
        if (!finalCron) { alert('Enter a schedule.'); return; }
        const res = await saveSchedule({
            id: editingId,
            name: name.trim(),
            target_type: targetType,
            target_id: targetId,
            cron: finalCron,
            enabled,
        });
        if (res.error) { alert(res.error); return; }
        await loadSchedules();
        onClose();
    }

    if (!isOpen) return null;

    const cron = currentCron();

    const inputClass = 'bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition';

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto border border-gray-200 dark:border-gray-700/60">
                    <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-t-2xl z-10">
                        <div class="flex items-center justify-between">
                            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">
                                ${editingId ? 'Edit Schedule' : 'New Schedule'}
                            </h2>
                            <button onClick=${onClose} class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="px-6 py-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">What should run?</label>
                            <div class="flex gap-2 mb-2">
                                <button onClick=${() => { setTargetType('profile'); setTargetId(''); }}
                                    class="flex-1 px-3 py-2 text-sm font-medium rounded-lg border transition ${targetType === 'profile'
                                        ? 'bg-violet-500/10 border-violet-500/40 text-violet-600 dark:text-violet-400'
                                        : 'bg-white dark:bg-gray-900/30 border-gray-300 dark:border-gray-700/60 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'}">
                                    Profile
                                </button>
                                <button onClick=${() => { setTargetType('workflow'); setTargetId(''); }}
                                    class="flex-1 px-3 py-2 text-sm font-medium rounded-lg border transition ${targetType === 'workflow'
                                        ? 'bg-violet-500/10 border-violet-500/40 text-violet-600 dark:text-violet-400'
                                        : 'bg-white dark:bg-gray-900/30 border-gray-300 dark:border-gray-700/60 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'}">
                                    Workflow
                                </button>
                            </div>
                            <select value=${targetId} onChange=${e => setTargetId(e.target.value)} class=${`w-full ${inputClass}`}>
                                <option value="">Select a ${targetType}...</option>
                                ${targetOptions.map(item => html`<option value=${item.id} selected=${targetId === item.id}>${esc(item.name)}</option>`)}
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Label <span class="text-gray-400 font-normal">(optional)</span></label>
                            <input type="text" value=${name} onInput=${e => setName(e.target.value)}
                                placeholder="e.g. Nightly backup"
                                class=${`w-full ${inputClass}`} />
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Schedule</label>
                            <div class="flex gap-2 mb-2">
                                <button onClick=${() => setMode('preset')}
                                    class="flex-1 px-3 py-2 text-sm font-medium rounded-lg border transition ${mode === 'preset'
                                        ? 'bg-violet-500/10 border-violet-500/40 text-violet-600 dark:text-violet-400'
                                        : 'bg-white dark:bg-gray-900/30 border-gray-300 dark:border-gray-700/60 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'}">
                                    Presets
                                </button>
                                <button onClick=${() => setMode('custom')}
                                    class="flex-1 px-3 py-2 text-sm font-medium rounded-lg border transition ${mode === 'custom'
                                        ? 'bg-violet-500/10 border-violet-500/40 text-violet-600 dark:text-violet-400'
                                        : 'bg-white dark:bg-gray-900/30 border-gray-300 dark:border-gray-700/60 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'}">
                                    Custom cron
                                </button>
                            </div>
                            ${mode === 'preset' ? html`
                                <div class="space-y-2">
                                    <select value=${presetKind} onChange=${e => setPresetKind(e.target.value)} class=${`w-full ${inputClass}`}>
                                        <option value="repeat" selected=${presetKind === 'repeat'}>Repeat every...</option>
                                        <option value="daily" selected=${presetKind === 'daily'}>Daily at a time</option>
                                        <option value="weekly" selected=${presetKind === 'weekly'}>Weekly on days at a time</option>
                                        <option value="monthly" selected=${presetKind === 'monthly'}>Monthly on a day at a time</option>
                                    </select>
                                    ${presetKind === 'repeat' ? html`
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">Every</span>
                                            <input type="number" min="1" max=${UNIT_MAX[repeatUnit]} value=${repeatN}
                                                onInput=${e => setRepeatN(clampN(e.target.value, repeatUnit))}
                                                class="w-20 ${inputClass}" />
                                            <select value=${repeatUnit}
                                                onChange=${e => { setRepeatUnit(e.target.value); setRepeatN(n => clampN(n, e.target.value)); }}
                                                class="flex-1 ${inputClass}">
                                                <option value="minutes" selected=${repeatUnit === 'minutes'}>minute${repeatN == 1 ? '' : 's'}</option>
                                                <option value="hours" selected=${repeatUnit === 'hours'}>hour${repeatN == 1 ? '' : 's'}</option>
                                                <option value="days" selected=${repeatUnit === 'days'}>day${repeatN == 1 ? '' : 's'}</option>
                                            </select>
                                        </div>
                                        ${repeatUnit === 'days' ? html`
                                            <div class="flex items-center gap-2">
                                                <span class="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">at</span>
                                                <input type="time" value=${repeatDaysTime} onInput=${e => setRepeatDaysTime(e.target.value)} class="flex-1 ${inputClass}" />
                                            </div>
                                            <p class="text-xs text-gray-500 dark:text-gray-400">Day counts from the 1st of the month.</p>
                                        ` : ''}
                                    ` : ''}
                                    ${presetKind === 'daily' ? html`
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">Every day at</span>
                                            <input type="time" value=${dailyTime} onInput=${e => setDailyTime(e.target.value)} class="flex-1 ${inputClass}" />
                                        </div>
                                    ` : ''}
                                    ${presetKind === 'weekly' ? html`
                                        <div class="flex flex-wrap gap-1.5">
                                            ${DAY_LABELS.map((label, d) => html`
                                                <button type="button" onClick=${() => toggleDay(d)}
                                                    class="px-2.5 py-1.5 text-xs font-medium rounded-lg border transition ${weeklyDays.includes(d)
                                                        ? 'bg-violet-500/10 border-violet-500/40 text-violet-600 dark:text-violet-400'
                                                        : 'bg-white dark:bg-gray-900/30 border-gray-300 dark:border-gray-700/60 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'}">
                                                    ${label}
                                                </button>
                                            `)}
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">at</span>
                                            <input type="time" value=${weeklyTime} onInput=${e => setWeeklyTime(e.target.value)} class="flex-1 ${inputClass}" />
                                        </div>
                                    ` : ''}
                                    ${presetKind === 'monthly' ? html`
                                        <div class="flex items-center gap-2">
                                            <span class="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">On day</span>
                                            <input type="number" min="1" max="31" value=${monthlyDay}
                                                onInput=${e => setMonthlyDay(clampN(e.target.value, 'days'))}
                                                class="w-20 ${inputClass}" />
                                            <span class="text-sm text-gray-500 dark:text-gray-400">of the month at</span>
                                            <input type="time" value=${monthlyTime} onInput=${e => setMonthlyTime(e.target.value)} class="flex-1 ${inputClass}" />
                                        </div>
                                        <p class="text-xs text-gray-500 dark:text-gray-400">Months without that day (e.g. Feb 30) simply skip.</p>
                                    ` : ''}
                                </div>
                            ` : html`
                                <input type="text" value=${cronInput} onInput=${e => setCronInput(e.target.value)}
                                    placeholder="*/15 * * * *"
                                    title="minute hour day-of-month month day-of-week — supports *, lists, ranges, and steps"
                                    class=${`w-full font-mono ${inputClass}`} />
                                <p class="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
                                    Fields: <span class="font-mono">minute hour day-of-month month day-of-week</span>.
                                    Supports <span class="font-mono">*</span>, lists (<span class="font-mono">1,5</span>), ranges (<span class="font-mono">9-17</span>) and steps (<span class="font-mono">*/15</span>).
                                    Day 0 and 7 are Sunday.
                                </p>
                            `}

                            <div class="mt-3 rounded-lg bg-gray-50 dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700/60 px-3 py-2.5 text-xs">
                                <div class="flex items-center justify-between gap-2">
                                    <span class="text-gray-500 dark:text-gray-400">Cron</span>
                                    <span class="font-mono text-gray-800 dark:text-gray-200">${esc(cron || '—')}</span>
                                </div>
                                ${preview && preview.description ? html`
                                    <div class="flex items-center justify-between gap-2 mt-1">
                                        <span class="text-gray-500 dark:text-gray-400">Meaning</span>
                                        <span class="text-gray-800 dark:text-gray-200 font-medium">${esc(preview.description)}</span>
                                    </div>
                                ` : ''}
                                ${preview && preview.next.length ? html`
                                    <div class="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700/60">
                                        <div class="text-gray-500 dark:text-gray-400 mb-1">Next runs</div>
                                        ${preview.next.map(n => html`
                                            <div class="flex items-center justify-between gap-2 text-gray-700 dark:text-gray-300 font-mono">
                                                <span>${esc(n.local)}</span>
                                            </div>
                                        `)}
                                    </div>
                                ` : ''}
                                ${previewError ? html`
                                    <div class="mt-1 text-red-600 dark:text-red-400">${esc(previewError)}</div>
                                ` : ''}
                            </div>
                        </div>
                        <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                            <input type="checkbox" checked=${enabled} onChange=${e => setEnabled(e.target.checked)}
                                class="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0" />
                            Enabled
                        </label>
                    </div>
                    <div class="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-b-2xl flex justify-end gap-2">
                        <button onClick=${onClose} class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Cancel</button>
                        <button onClick=${handleSave} class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-4 py-2 rounded-lg transition">Save Schedule</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}
