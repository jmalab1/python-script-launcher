import { html } from '../../vendor/standalone-preact.esm.js';
import { profiles } from '../state.js';
import { saveProfileOrder } from '../api.js';
import { ProfileCard } from './ProfileCard.js';
import { SortableList } from './SortableList.js';

export function ProfileList({ onEdit, onRun }) {
    if (!profiles.value.length) {
        return html`
            <div class="text-center py-16 text-gray-500 dark:text-gray-400">
                <div class="text-4xl mb-3">📄</div>
                <p>No profiles yet. Create one to get started.</p>
            </div>
        `;
    }

    return html`
        <${SortableList}
            items=${profiles.value}
            onReorder=${(next) => {
                profiles.value = next;
                saveProfileOrder(next.map(p => p.id));
            }}
            renderItem=${(p) => html`<${ProfileCard} profile=${p} onEdit=${onEdit} onRun=${onRun} />`}
        />
    `;
}
