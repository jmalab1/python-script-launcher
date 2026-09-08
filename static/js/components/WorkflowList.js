import { html } from '../../vendor/standalone-preact.esm.js';
import { workflows, tags, selectedWorkflowTag } from '../state.js';
import { saveWorkflowOrder } from '../api.js';
import { WorkflowCard } from './WorkflowCard.js';
import { ItemList } from './ItemList.js';
import { TagFilter } from './TagFilter.js';

export function WorkflowList({ onEdit, onRun }) {
    if (!workflows.value.length) {
        return html`
            <div class="text-center py-16 text-gray-500 dark:text-gray-400">
                <div class="text-4xl mb-3">🔌</div>
                <p>No workflows yet. Create one to chain profiles.</p>
            </div>
        `;
    }

    return html`
        <${TagFilter}
            tags=${tags.value}
            items=${workflows.value}
            getTags=${(w) => w.tags || []}
            selectedTag=${selectedWorkflowTag.value}
            onSelect=${(v) => { selectedWorkflowTag.value = v; }}
        />
        <${ItemList}
            items=${workflows.value}
            getTags=${(w) => w.tags || []}
            selectedTag=${selectedWorkflowTag.value}
            onReorder=${(next) => {
                workflows.value = next;
                saveWorkflowOrder(next.map(w => w.id));
            }}
            renderItem=${(w) => html`<${WorkflowCard} workflow=${w} onEdit=${onEdit} onRun=${onRun} />`}
            emptyMessage="No workflows with this tag."
        />
    `;
}
