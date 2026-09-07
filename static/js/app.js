import { html, render } from '../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../vendor/standalone-preact.esm.js';
import {
    profiles, workflows, currentPanel, theme, sidebarOpen,
    profileHistoryData, workflowHistoryData,
    profileHistoryPage, workflowHistoryPage,
} from './state.js';
import {
    loadProfiles, loadWorkflows, checkAllScripts,
    loadProfileHistory, loadWorkflowHistory,
} from './api.js';
import { Sidebar, MobileHeader } from './components/Sidebar.js';
import { ProfileList } from './components/ProfileList.js';
import { ProfileModal } from './components/ProfileModal.js';
import { WorkflowList } from './components/WorkflowList.js';
import { WorkflowModal } from './components/WorkflowModal.js';
import { HistoryTable } from './components/HistoryTable.js';
import { RunModal } from './components/RunModal.js';

function App() {
    const [initialized, setInitialized] = useState(false);
    const [profileTimer, setProfileTimer] = useState(null);
    const [workflowTimer, setWorkflowTimer] = useState(null);

    const [runOpen, setRunOpen] = useState(false);
    const [runId, setRunId] = useState(null);
    const [runTitle, setRunTitle] = useState('Run Output');
    const [runType, setRunType] = useState(null);

    const [profileOpen, setProfileOpen] = useState(false);
    const [editingProfile, setEditingProfile] = useState(null);

    const [workflowOpen, setWorkflowOpen] = useState(false);
    const [editingWorkflow, setEditingWorkflow] = useState(null);

    useEffect(() => {
        async function init() {
            await loadProfiles();
            await loadWorkflows();
            await checkAllScripts();
            await loadProfileHistory();
            setInitialized(true);
        }
        init();
    }, []);

    useEffect(() => {
        if (!initialized) return;

        if (profileTimer) clearInterval(profileTimer);
        if (workflowTimer) clearInterval(workflowTimer);

        if (currentPanel.value === 'profiles') {
            loadProfileHistory();
            const t = setInterval(loadProfileHistory, 3000);
            setProfileTimer(t);
        }
        if (currentPanel.value === 'workflows') {
            loadWorkflowHistory();
            const t = setInterval(loadWorkflowHistory, 3000);
            setWorkflowTimer(t);
        }

        return () => {
            if (profileTimer) clearInterval(profileTimer);
            if (workflowTimer) clearInterval(workflowTimer);
        };
    }, [currentPanel.value, initialized]);

    function openNewProfileModal() {
        setEditingProfile(null);
        setProfileOpen(true);
    }

    function openNewWorkflowModal() {
        setEditingWorkflow(null);
        setWorkflowOpen(true);
    }

    function openRunModal(id, title, type) {
        setRunId(id);
        setRunTitle(title || 'Run Output');
        setRunType(type || null);
        setRunOpen(true);
    }

    function handleRunStarted(id, title) {
        openRunModal(id, title, null);
    }

    if (!initialized) {
        return html`<div class="flex h-screen items-center justify-center text-gray-500">Loading...</div>`;
    }

    return html`
        <div class="flex h-screen">
            <${Sidebar} />
            <${MobileHeader} />

            <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
                <div class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900">
                    <div class="flex flex-col px-4 sm:px-6 lg:px-8 py-6 w-full min-h-full">

                        ${currentPanel.value === 'profiles' ? html`
                            <div id="panel-profiles" class="panel">
                                <div class="flex items-center justify-between mb-6">
                                    <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Profiles</h1>
                                    <button onClick=${openNewProfileModal}
                                        class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                        New Profile
                                    </button>
                                </div>
                                <div class="grid grid-cols-1 xl:grid-cols-5 gap-6">
                                    <div class="xl:col-span-2">
                                        <${ProfileList} onEdit=${(p) => { setEditingProfile(p); setProfileOpen(true); }} onRun=${handleRunStarted} />
                                    </div>
                                    <div class="xl:col-span-3">
                                        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60">
                                            <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60">
                                                <h2 class="font-semibold text-gray-800 dark:text-gray-100">Profile Run History</h2>
                                            </header>
                                            <div class="p-3">
                                                <${HistoryTable} data=${profileHistoryData.value} pageSignal=${profileHistoryPage} onLoad=${loadProfileHistory} type="profile" onOpenRun=${openRunModal} />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                        ${currentPanel.value === 'workflows' ? html`
                            <div id="panel-workflows" class="panel xl:flex xl:flex-col xl:h-[calc(100vh-6.75rem)]">
                                <div class="flex items-center justify-between mb-6 xl:shrink-0">
                                    <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Workflows</h1>
                                    <button onClick=${openNewWorkflowModal}
                                        class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                        New Workflow
                                    </button>
                                </div>
                                <div class="grid grid-cols-1 xl:grid-cols-5 gap-6 xl:flex-1 xl:min-h-0">
                                    <div class="xl:col-span-2 xl:overflow-y-auto xl:pr-1">
                                        <${WorkflowList} onEdit=${(w) => { setEditingWorkflow(w); setWorkflowOpen(true); }} onRun=${handleRunStarted} />
                                    </div>
                                    <div class="xl:col-span-3 xl:overflow-y-auto xl:pr-1">
                                        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60">
                                            <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60">
                                                <h2 class="font-semibold text-gray-800 dark:text-gray-100">Run History</h2>
                                            </header>
                                            <div class="p-3">
                                                <${HistoryTable} data=${workflowHistoryData.value} pageSignal=${workflowHistoryPage} onLoad=${loadWorkflowHistory} type="workflow" onOpenRun=${openRunModal} />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                    </div>
                </div>
            </div>

            <${ProfileModal} isOpen=${profileOpen} onClose=${() => setProfileOpen(false)} profile=${editingProfile} />
            <${WorkflowModal} isOpen=${workflowOpen} onClose=${() => setWorkflowOpen(false)} workflow=${editingWorkflow} />
            <${RunModal} isOpen=${runOpen} onClose=${() => setRunOpen(false)} runId=${runId} title=${runTitle} runType=${runType} />
        </div>
    `;
}

render(html`<${App} />`, document.getElementById('app'));
