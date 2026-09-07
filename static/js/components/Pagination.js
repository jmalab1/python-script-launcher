import { html } from '../../vendor/standalone-preact.esm.js';
import { esc } from '../utils.js';

export function Pagination({ data, pageSignal, onLoad }) {
    if (!data || data.pages <= 1) return null;

    const pages = [];
    for (let i = Math.max(1, data.page - 2); i <= Math.min(data.pages, data.page + 2); i++) {
        pages.push(i);
    }

    return html`
        <div class="mt-3 flex items-center justify-center gap-1">
            <button onClick=${() => { pageSignal.value = 1; onLoad(); }}
                disabled=${data.page === 1}
                class="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 transition">«</button>
            <button onClick=${() => { pageSignal.value = Math.max(1, pageSignal.value - 1); onLoad(); }}
                disabled=${data.page === 1}
                class="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 transition">‹</button>
            ${pages.map(i => html`
                <button onClick=${() => { pageSignal.value = i; onLoad(); }}
                    class="px-2 py-1 rounded text-xs ${i === data.page
                        ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
                        : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700'} transition">${i}</button>
            `)}
            <button onClick=${() => { pageSignal.value = Math.min(data.pages, pageSignal.value + 1); onLoad(); }}
                disabled=${data.page === data.pages}
                class="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 transition">›</button>
            <button onClick=${() => { pageSignal.value = data.pages; onLoad(); }}
                disabled=${data.page === data.pages}
                class="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700/60 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-30 transition">»</button>
            <span class="text-xs text-gray-400 ml-2">${data.total} total</span>
        </div>
    `;
}
