import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';
import { saveProfile, loadProfiles, checkAllScripts, openNativeFileDialog } from '../api.js';

export function ProfileModal({ isOpen, onClose, profile }) {
    const [name, setName] = useState('');
    const [scriptPath, setScriptPath] = useState('');
    const [args, setArgs] = useState('');
    const [customArgs, setCustomArgs] = useState([]);
    const [editingId, setEditingId] = useState(null);

    useEffect(() => {
        if (isOpen) {
            if (profile) {
                setEditingId(profile.id);
                setName(profile.name || '');
                setScriptPath(profile.script_path || '');
                setArgs((profile.args || []).join('\n'));
                setCustomArgs(JSON.parse(JSON.stringify(profile.custom_args || [])));
            } else {
                setEditingId(null);
                setName('');
                setScriptPath('');
                setArgs('');
                setCustomArgs([]);
            }
        }
    }, [isOpen, profile]);

    function addCustomArg() {
        setCustomArgs([...customArgs, { name: '', label: '', type: 'text', default: '', value: '' }]);
    }

    function removeCustomArg(idx) {
        setCustomArgs(customArgs.filter((_, i) => i !== idx));
    }

    function updateCustomArg(idx, field, val) {
        setCustomArgs(customArgs.map((ca, i) => i === idx ? { ...ca, [field]: val } : ca));
    }

    async function handleSave() {
        const trimmedName = name.trim();
        const trimmedScript = scriptPath.trim();
        if (!trimmedName || !trimmedScript) { alert('Name and script path are required.'); return; }
        const argsList = args.trim() ? args.trim().split('\n').map(s => s.trim()).filter(Boolean) : [];
        const builtCustomArgs = customArgs.map(ca => {
            const built = {
                name: ca.name.trim(), label: (ca.label || ca.name).trim(),
                type: ca.type || 'text', default: ca.default || '', value: ca.value || ca.default || '',
            };
            if (built.type === 'date') built.format = (ca.format || '').trim();
            if (built.type === 'enum') built.options = (ca.options || '').trim();
            return built;
        }).filter(ca => ca.name);
        await saveProfile({ id: editingId, name: trimmedName, script_path: trimmedScript, args: argsList, custom_args: builtCustomArgs });
        await loadProfiles();
        await checkAllScripts();
        onClose();
    }

    async function handleBrowse() {
        const data = await openNativeFileDialog();
        if (data.error) { alert(data.error); return; }
        if (data.path) setScriptPath(data.path);
    }

    if (!isOpen) return null;

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-y-auto border border-gray-200 dark:border-gray-700/60">
                    <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-t-2xl z-10">
                        <div class="flex items-center justify-between">
                            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">
                                ${editingId ? 'Edit Profile' : 'New Profile'}
                            </h2>
                            <button onClick=${onClose} class="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="px-6 py-5 space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Profile Name</label>
                            <input type="text" value=${name} onInput=${e => setName(e.target.value)}
                                placeholder="e.g. Data Pipeline"
                                class="w-full bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Script Path</label>
                            <div class="flex gap-2">
                                <input type="text" value=${scriptPath} readonly
                                    placeholder="No file selected"
                                    class="flex-1 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 cursor-default" />
                                <button onClick=${handleBrowse}
                                    class="bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm font-medium px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700/60 transition whitespace-nowrap">Browse</button>
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Arguments <span class="text-gray-400 font-normal">(one per line)</span></label>
                            <textarea rows="3" value=${args} onInput=${e => setArgs(e.target.value)}
                                placeholder=${"--input data.csv\n--verbose"}
                                class="w-full bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded-lg px-3 py-2 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 font-mono focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition resize-y"></textarea>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Custom Argument Fields</label>
                            <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Define named fields that appear as editable inputs on the profile card.</p>
                            <div class="space-y-2">
                                ${!customArgs.length ? html`
                                    <div class="text-xs text-gray-400 py-2">No custom fields defined.</div>
                                ` : customArgs.map((ca, i) => html`
                                    <div class="flex items-center flex-wrap gap-2 p-2 bg-gray-50 dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700/60 rounded-lg">
                                        <input type="text" value=${ca.name} placeholder="Flag (--name)"
                                            onInput=${e => updateCustomArg(i, 'name', e.target.value)}
                                            class="flex-1 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                        <input type="text" value=${ca.label || ''} placeholder="Label"
                                            onInput=${e => updateCustomArg(i, 'label', e.target.value)}
                                            class="flex-1 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                        <select onChange=${e => updateCustomArg(i, 'type', e.target.value)}
                                            class="bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition">
                                            <option value="text" selected=${ca.type === 'text'}>Text</option>
                                            <option value="checkbox" selected=${ca.type === 'checkbox'}>Checkbox</option>
                                            <option value="date" selected=${ca.type === 'date'}>Date</option>
                                            <option value="enum" selected=${ca.type === 'enum'}>Enum</option>
                                        </select>
                                        ${ca.type !== 'checkbox' ? html`
                                            <input type=${ca.type === 'date' ? 'date' : 'text'} value=${ca.default || ''} placeholder="Default"
                                                onInput=${e => updateCustomArg(i, 'default', e.target.value)}
                                                class="flex-1 min-w-[9rem] bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                        ` : ''}
                                        ${ca.type === 'date' ? html`
                                            <input type="text" value=${ca.format || ''} placeholder="Format (%Y-%m-%d)"
                                                title="strftime-style format applied when the script runs, e.g. %d/%m/%Y — defaults to %Y-%m-%d"
                                                onInput=${e => updateCustomArg(i, 'format', e.target.value)}
                                                class="flex-1 min-w-[9rem] bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs font-mono text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                        ` : ''}
                                        ${ca.type === 'enum' ? html`
                                            <input type="text" value=${ca.options || ''} placeholder="Options (comma-separated)"
                                                title="Comma-separated choices for the dropdown, e.g. debug, info, warn"
                                                onInput=${e => updateCustomArg(i, 'options', e.target.value)}
                                                class="flex-1 min-w-[9rem] bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                        ` : ''}
                                        <button onClick=${() => removeCustomArg(i)} class="p-1 text-gray-400 hover:text-red-500 transition">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>
                                        </button>
                                    </div>
                                `)}
                            </div>
                            ${customArgs.some(ca => ca.type === 'date') ? html`
                                <div class="mt-2 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                                    <span class="font-medium text-gray-600 dark:text-gray-300">Date format</span> — strftime-style tokens applied when the script runs.
                                    Example: <span class="font-mono">%d/%m/%Y</span> → 07/09/2026, <span class="font-mono">%d.%m.%y</span> → 07.09.26.
                                    Tokens: <span class="font-mono">%Y</span> 2026, <span class="font-mono">%y</span> 26, <span class="font-mono">%m</span> 09, <span class="font-mono">%d</span> 07, <span class="font-mono">%B</span> September, <span class="font-mono">%b</span> Sep.
                                    Leave blank for <span class="font-mono">%Y-%m-%d</span>.
                                </div>
                            ` : ''}
                            ${customArgs.some(ca => ca.type === 'enum') ? html`
                                <div class="mt-2 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                                    <span class="font-medium text-gray-600 dark:text-gray-300">Enum options</span> — comma-separated choices for the dropdown, e.g. <span class="font-mono">debug, info, warn</span>.
                                    The argument is only passed to the script when a value is selected.
                                </div>
                            ` : ''}
                            <button onClick=${addCustomArg} class="mt-2 text-xs text-violet-500 hover:text-violet-600 font-medium">+ Add Argument Field</button>
                        </div>
                    </div>
                    <div class="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700/60 px-6 py-4 rounded-b-2xl flex justify-end gap-2">
                        <button onClick=${onClose} class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition">Cancel</button>
                        <button onClick=${handleSave} class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-4 py-2 rounded-lg transition">Save Profile</button>
                    </div>
                </div>
            </div>
        </div>
    `;
}
