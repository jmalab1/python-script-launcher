import { html, useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { loadSettings, saveSettings } from '../api.js';

// The Settings panel edits server-side options. Today that is one
// option: the Python runtime location used to run user scripts.
export function SettingsPanel() {
    const [config, setConfig] = useState(null);
    const [path, setPath] = useState('');
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadSettings().then(data => {
            setConfig(data);
            setPath(data.runtime_path || '');
        }).catch(err => setError('Could not load the settings: ' + err.message));
    }, []);

    async function save(next) {
        setError('');
        setNotice('');
        setSaving(true);
        try {
            const data = await saveSettings(next);
            setConfig(data);
            setPath(data.runtime_path || '');
            setNotice(next
                ? 'Runtime saved — new runs use it from now on.'
                : 'Runtime cleared — the packaged runtime is used again.');
        } catch (err) {
            setError('Could not save the settings: ' + err.message);
        } finally {
            setSaving(false);
        }
    }

    function submit(e) {
        e.preventDefault();
        save(path.trim());
    }

    function usePackaged() {
        save('');
    }

    if (!config) {
        return html`<p class="text-sm text-gray-500 dark:text-gray-400">${error || 'Loading settings...'}</p>`;
    }

    return html`
        <div class="max-w-2xl space-y-6">
            ${error ? html`<div class="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 px-4 py-3 text-sm text-red-700 dark:text-red-300">${error}</div>` : ''}
            ${notice ? html`<div class="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/30 px-4 py-3 text-sm text-green-700 dark:text-green-300">${notice}</div>` : ''}

            <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60">
                <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60">
                    <h2 class="font-semibold text-gray-800 dark:text-gray-100">Python Runtime</h2>
                    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Where to find Python for running scripts. Scripts with extra pip packages need a runtime that has them installed.</p>
                </div>
                <form onSubmit=${submit} class="p-5 space-y-4">
                    <label class="block">
                        <span class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Runtime location</span>
                        <input type="text" value=${path}
                            onInput=${e => setPath(e.target.value)}
                            placeholder="e.g. /opt/python/bin/python3 or a venv directory"
                            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
                        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1.5">A python interpreter file, or a Python install / virtualenv directory. A leading ~ is resolved to your home directory.</p>
                    </label>
                    <div class="text-sm text-gray-600 dark:text-gray-400">
                        Currently running scripts with:
                        <code class="ml-1 text-xs bg-gray-100 dark:bg-gray-900 px-1.5 py-0.5 rounded break-all">${config.effective_interpreter}</code>
                    </div>
                    <div class="flex items-center gap-3">
                        <button type="submit" disabled=${saving}
                            class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg transition disabled:opacity-50">Save</button>
                        <button type="button" onClick=${usePackaged} disabled=${saving || !config.runtime_path}
                            class="bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm font-medium px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700/60 transition disabled:opacity-50">Use packaged runtime</button>
                    </div>
                </form>
            </div>
        </div>
    `;
}
