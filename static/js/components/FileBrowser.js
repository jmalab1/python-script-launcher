// FileBrowser: an in-app script picker that drives the /api/browse
// explorer. It replaces the native file dialog — the Go binary cannot
// spawn platform dialogs, so "Browse" opens this overlay instead.
import { html } from '../../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../../vendor/standalone-preact.esm.js';
import { browseDirectory } from '../api.js';
import { ErrorBanner } from './ErrorBanner.js';

export function FileBrowser({ isOpen, onClose, onSelect, initialPath, initialDir }) {
    const [cwd, setCwd] = useState(initialDir || '');
    const [entries, setEntries] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!isOpen) return;
        setError('');
        setSelectedFile(null);
        // Start in the profile's own directory when there is one,
        // otherwise at the file the user already has.
        load(initialDir || initialPath || '');
    }, [isOpen]);    // eslint-disable-line react-hooks/exhaustive-deps

    async function load(path) {
        setLoading(true);
        setError('');
        try {
            const data = await browseDirectory(path);
            if (data.error) {
                setError(data.error);
                setLoading(false);
                return;
            }
            setCwd(data.path);
            setEntries(data.entries || []);
            if (data.selected_file) setSelectedFile(data.selected_file);
        } catch (err) {
            setError(err.message || 'Could not open the directory.');
        }
        setLoading(false);
    }

    if (!isOpen) return null;

    const pick = (entry) => {
        if (entry.is_dir) {
            setSelectedFile(null);
            load(entry.path);
        } else {
            setSelectedFile({ name: entry.name, path: entry.path, is_dir: false });
        }
    };

    const confirm = () => {
        if (!selectedFile) return;
        onSelect(selectedFile.path);
        onClose();
    };

    return html`
        <div class="fixed inset-0 z-[60]">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4 pointer-events-none">
                <div class="pointer-events-auto bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-gray-200 dark:border-gray-700/60">
                    <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700/60">
                        <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">Select Python Script</h2>
                    </div>
                    <div class="px-6 pt-3">
                        <!-- current directory + navigation, terminal-style -->
                        <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                            <span class="truncate font-mono bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded flex-1">${cwd || '–'}</span>
                            <button onClick=${() => load(cwd)}
                                class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700">Reload</button>
                            <button onClick=${() => load('')}
                                class="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700">Home</button>
                        </div>
                    </div>
                    ${error ? html`<div class="px-6 pt-3"><${ErrorBanner} message=${error} onDismiss=${() => setError('')} /></div>` : ''}
                    <div class="flex-1 overflow-y-auto px-6 py-3 min-h-[12rem]">
                        ${loading ? html`<p class="text-sm text-gray-500 dark:text-gray-400">Loading…</p>` : html`
                            <ul class="divide-y divide-gray-100 dark:divide-gray-700/60">
                                ${entries.map(entry => html`
                                    <li key=${entry.path}>
                                        <button onClick=${() => pick(entry)}
                                            onDblClick=${() => entry.is_dir ? pick(entry) : confirm()}
                                            class="w-full text-left flex items-center gap-2 px-2 py-2 rounded-lg text-sm
                                                ${selectedFile && selectedFile.path === entry.path
                                                    ? 'bg-indigo-50 dark:bg-indigo-900/40'
                                                    : 'hover:bg-gray-100 dark:hover:bg-gray-700/60'}">
                                            ${entry.is_dir
                                                ? html`<svg class="w-4 h-4 text-indigo-500 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>`
                                                : html`<svg class="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6M7 3h7l5 5v13H7V3z"/></svg>`}
                                            <span class=${entry.is_dir ? '' : 'font-mono'}
                                                title=${entry.path}>${entry.name}</span>
                                        </button>
                                    </li>`)}
                                ${!entries.length ? html`<li class="text-sm text-gray-500 dark:text-gray-400 py-2">Empty directory.</li>` : ''}
                            </ul>`}
                    </div>
                    <div class="px-6 py-4 border-t border-gray-200 dark:border-gray-700/60 flex items-center justify-between">
                        <p class="text-xs text-gray-400">Python scripts (.py, .pyw) only</p>
                        <div class="flex gap-2">
                            <button onClick=${onClose}
                                class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">Cancel</button>
                            <button onClick=${confirm} disabled=${!selectedFile}
                                class="px-4 py-2 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed">Select</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}
