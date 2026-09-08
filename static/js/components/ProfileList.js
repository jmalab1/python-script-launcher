import { html } from '../../vendor/standalone-preact.esm.js';
import { profiles, profileFolders, selectedProfileFolder } from '../state.js';
import { saveProfileOrder } from '../api.js';
import { ProfileCard } from './ProfileCard.js';
import { GroupedSortableList } from './GroupedSortableList.js';
import { FolderFilter } from './FolderFilter.js';

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
        <${FolderFilter}
            folders=${profileFolders.value}
            items=${profiles.value}
            getFolder=${(p) => p.group || ''}
            selectedFolder=${selectedProfileFolder.value}
            onSelect=${(v) => { selectedProfileFolder.value = v; }}
        />
        <${GroupedSortableList}
            items=${profiles.value}
            folders=${profileFolders.value}
            getFolder=${(p) => p.group || ''}
            selectedFolder=${selectedProfileFolder.value}
            onReorder=${(next) => {
                profiles.value = next;
                saveProfileOrder(next.map(p => p.id));
            }}
            renderItem=${(p) => html`<${ProfileCard} profile=${p} onEdit=${onEdit} onRun=${onRun} />`}
            emptyMessage="No profiles in this folder."
        />
    `;
}
