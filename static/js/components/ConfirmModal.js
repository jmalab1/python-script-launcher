import { html } from '../../vendor/standalone-preact.esm.js';
import { useState } from '../../vendor/standalone-preact.esm.js';

export function ConfirmModal({ isOpen, onClose, onConfirm, title, message, confirmLabel = 'Delete' }) {
    const [busy, setBusy] = useState(false);
    if (!isOpen) return null;

    async function handleConfirm() {
        if (busy) return;
        setBusy(true);
        try {
            await onConfirm();
            onClose();
        } finally {
            setBusy(false);
        }
    }

    return html`
        <div class="fixed inset-0 z-50">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick=${onClose}></div>
            <div class="relative flex items-center justify-center min-h-full p-4">
                <div class="relative bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-sm border border-gray-200 dark:border-gray-700/60 p-6">
                    <div class="flex items-start gap-4">
                        <span class="shrink-0 flex items-center justify-center w-10 h-10 rounded-full bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
                        </span>
                        <div class="min-w-0">
                            <h3 class="text-base font-semibold text-gray-800 dark:text-gray-100">${title || 'Are you sure?'}</h3>
                            <div class="mt-1 text-sm text-gray-500 dark:text-gray-400">${message}</div>
                        </div>
                    </div>
                    <div class="mt-5 flex justify-end gap-2">
                        <button onClick=${onClose} disabled=${busy}
                            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition disabled:opacity-50">Cancel</button>
                        <button onClick=${handleConfirm} disabled=${busy}
                            class="px-4 py-2 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed">
                            ${busy ? 'Deleting...' : confirmLabel}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}
