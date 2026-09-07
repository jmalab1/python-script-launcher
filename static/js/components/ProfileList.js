import { html } from '../../vendor/standalone-preact.esm.js';
import { profiles } from '../state.js';
import { ProfileCard } from './ProfileCard.js';

export function ProfileList({ onEdit, onRun }) {
    if (!profiles.value.length) {
        return html`
            <div class="text-center py-16 text-gray-500 dark:text-gray-400">
                <div class="text-4xl mb-3">&#128196;</div>
                <p>No profiles yet. Create one to get started.</p>
            </div>
        `;
    }

    return html`
        <div class="space-y-3">
            ${profiles.value.map(p => html`<${ProfileCard} key=${p.id} profile=${p} onEdit=${onEdit} onRun=${onRun} />`)}
        </div>
    `;
}
