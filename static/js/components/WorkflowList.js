import { html } from '../../vendor/standalone-preact.esm.js';
import { workflows, workflowFolders, selectedWorkflowFolder } from '../state.js';
import { saveWorkflowOrder } from '../api.js';
import { WorkflowCard } from './WorkflowCard.js';
import { GroupedSortableList } from './GroupedSortableList.js';
import { FolderFilter } from './FolderFilter.js';

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
        <${FolderFilter}
            folders=${workflowFolders.value}
            items=${workflows.value}
            getFolder=${(w) => w.group || ''}
            selectedFolder=${selectedWorkflowFolder.value}
            onSelect=${(v) => { selectedWorkflowFolder.value = v; }}
        />
        <${GroupedSortableList}
            items=${workflows.value}
            folders=${workflowFolders.value}
            getFolder=${(w) => w.group || ''}
            selectedFolder=${selectedWorkflowFolder.value}
            onReorder=${(next) => {
                workflows.value = next;
                saveWorkflowOrder(next.map(w => w.id));
            }}
            renderItem=${(w) => html`<${WorkflowCard} workflow=${w} onEdit=${onEdit} onRun=${onRun} />`}
            emptyMessage="No workflows in this folder."
        />
    `;
}
