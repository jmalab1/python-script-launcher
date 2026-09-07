import { html } from '../../vendor/standalone-preact.esm.js';
import { workflows } from '../state.js';
import { WorkflowCard } from './WorkflowCard.js';

export function WorkflowList({ onEdit, onRun }) {
    if (!workflows.value.length) {
        return html`
            <div class="text-center py-16 text-gray-500 dark:text-gray-400">
                <div class="text-4xl mb-3">&#128268;</div>
                <p>No workflows yet. Create one to chain profiles.</p>
            </div>
        `;
    }

    return html`
        <div class="space-y-3">
            ${workflows.value.map(w => html`<${WorkflowCard} key=${w.id} workflow=${w} onEdit=${onEdit} onRun=${onRun} />`)}
        </div>
    `;
}
