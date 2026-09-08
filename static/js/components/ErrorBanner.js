import { html } from '../../vendor/standalone-preact.esm.js';

// Inline, non-blocking error message for modals. It replaces native
// browser dialogs: it cannot steal focus or block clicks, and it stays
// visible until the next action clears it.
export function ErrorBanner({ message }) {
    if (!message) return null;
    return html`
        <div role="alert"
            class="flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
            <svg class="w-4 h-4 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
            <span class="min-w-0 break-words">${message}</span>
        </div>
    `;
}
