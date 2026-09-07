import { html } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';
import { scriptStatusCache } from '../state.js';
import { runProfile, saveProfile as apiSaveProfile, loadProfiles } from '../api.js';

export function ProfileCard({ profile, onEdit, onRun }) {
    const p = profile;
    const cache = scriptStatusCache.value;
    const scriptMissing = cache[p.script_path] === false;
    const ca = p.custom_args || [];
    const sa = p.args || [];

    async function handleRun() {
        if (scriptMissing) return;
        const argValues = {};
        if (p.custom_args) p.custom_args.forEach((ca, i) => {
            const el = document.getElementById(`arg-${p.id}-${i}`);
            if (el) argValues[ca.name] = ca.type === 'checkbox' ? (el.checked ? 'true' : 'false') : el.value;
        });
        const res = await runProfile(p.id, argValues);
        if (res.run_id && onRun) onRun(res.run_id, 'Profile Run');
    }

    async function handleDelete() {
        if (!confirm('Delete this profile?')) return;
        const { deleteProfile } = await import('../api.js');
        await deleteProfile(p.id);
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
            ${esc(p.script_path)}
        </span>`
        : html`<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">${esc(p.script_path)}</span>`;

    return html`
        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl p-4 border ${scriptMissing ? 'border-red-200 dark:border-red-500/30' : 'border-gray-200 dark:border-gray-700/60'} hover:border-gray-300 dark:hover:border-gray-600 transition group">
            <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                    <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100">${esc(p.name)}</h3>
                    <div class="flex flex-wrap items-center gap-1.5 mt-2">
                        ${scriptBadge}
                        ${sa.map(a => html`<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-600 dark:text-violet-400">${esc(a)}</span>`)}
                    </div>
                    ${ca.length ? html`
                        <div class="flex flex-wrap items-center gap-3 mt-3">
                            ${ca.map((c, i) => {
                                if (c.type === 'checkbox') return html`
                                    <label class="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300 cursor-pointer">
                                        <input type="checkbox" id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                            onChange=${(e) => handleArgChange(e.target)}
                                            class="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900/30 text-violet-500 focus:ring-violet-500/50 focus:ring-offset-0" />
                                        ${esc(c.label || c.name)}
                                    </label>`;
                                return html`
                                    <div class="flex items-center gap-1.5">
                                        <label class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">${esc(c.label || c.name)}</label>
                                        <input type="text" id=${`arg-${p.id}-${i}`} data-profile=${p.id} data-idx=${i}
                                            value=${esc(c.value || c.default || '')}
                                            onChange=${(e) => handleArgChange(e.target)}
                                            placeholder=${esc(c.name)}
                                            class="w-32 bg-white dark:bg-gray-900/30 border border-gray-300 dark:border-gray-700/60 rounded px-2 py-1 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 focus:ring-0 focus:ring-offset-0 transition" />
                                    </div>`;
                            })}
                        </div>
                    ` : ''}
                </div>
                <div class="flex items-center gap-1 shrink-0">
                    <button onClick=${handleRun} disabled=${scriptMissing}
                        title=${scriptMissing ? 'Script not found' : ''}
                        class="inline-flex items-center gap-1 px-2.5 py-1.5 ${scriptMissing
                            ? 'bg-gray-100 dark:bg-gray-700/50 text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-700/60 cursor-not-allowed'
                            : 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/20 hover:bg-green-100 dark:hover:bg-green-500/20'} text-xs font-medium rounded-lg transition">
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Run
                    </button>
                    <button onClick=${() => onEdit && onEdit(p)}
                        class="px-2.5 py-1.5 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 transition">Edit</button>
                    <button onClick=${handleDelete}
                        class="px-2.5 py-1.5 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 text-xs font-medium rounded-lg border border-red-200 dark:border-red-500/20 hover:bg-red-100 dark:hover:bg-red-500/20 transition">Del</button>
                </div>
            </div>
        </div>
    `;
}
