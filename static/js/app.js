import { html, render } from '../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../vendor/standalone-preact.esm.js';
import {
    profiles, workflows, currentPanel, theme, sidebarOpen, PANELS,
    profileHistoryData, workflowHistoryData,
    profileHistoryPage, workflowHistoryPage,
    auditData, auditPage,
} from './state.js';
import {
    loadProfiles, loadWorkflows, checkAllScripts,
    loadProfileHistory, loadWorkflowHistory,
    loadAudit,
} from './api.js';
import { Sidebar, MobileHeader } from './components/Sidebar.js';
import { ProfileList } from './components/ProfileList.js';
import { ProfileModal } from './components/ProfileModal.js';
import { WorkflowList } from './components/WorkflowList.js';
import { WorkflowModal } from './components/WorkflowModal.js';
import { HistoryTable } from './components/HistoryTable.js';
import { AuditTable } from './components/AuditTable.js';
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
        function onHashChange() {
            const name = location.hash.replace(/^#\/?/, '');
            if (PANELS.includes(name) && name !== currentPanel.value) {
                currentPanel.value = name;
                localStorage.setItem('panel', name);
            }
        }
        window.addEventListener('hashchange', onHashChange);
        return () => window.removeEventListener('hashchange', onHashChange);
    }, []);

    useEffect(() => {
        async function init() {
            await Promise.all([loadProfiles(), loadWorkflows(), loadProfileHistory()]);
            await checkAllScripts();
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
        if (currentPanel.value === 'audit') {
            loadAudit();
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
                            <div id="panel-profiles" class="panel xl:flex xl:flex-col xl:h-[calc(100vh-8.25rem)]">
                                <div class="flex items-center justify-between mb-6 xl:shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Profiles</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Reusable script presets — point one at a Python script, add its arguments, and run it anytime.</p>
                                    </div>
                                    <button onClick=${openNewProfileModal}
                                        class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                        New Profile
                                    </button>
                                </div>
                                <div class="grid grid-cols-1 xl:grid-cols-5 gap-6 xl:flex-1 xl:min-h-0">
                                    <div class="xl:col-span-2 xl:overflow-y-auto xl:pr-1">
                                        <${ProfileList} onEdit=${(p) => { setEditingProfile(p); setProfileOpen(true); }} onRun=${handleRunStarted} />
                                    </div>
                                    <div class="xl:col-span-3 xl:overflow-y-auto xl:pr-1">
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
                            <div id="panel-workflows" class="panel xl:flex xl:flex-col xl:h-[calc(100vh-8.25rem)]">
                                <div class="flex items-center justify-between mb-6 xl:shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Workflows</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Chain profiles into ordered steps or parallel groups and run them all with a single click.</p>
                                    </div>
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

                        ${currentPanel.value === 'audit' ? html`
                            <div id="panel-audit" class="panel">
                                <div class="flex items-center justify-between mb-6">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Audit</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Who did what, when — every profile and workflow addition, edit, deletion, and reorder, with before/after snapshots.</p>
                                    </div>
                                </div>
                                <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60">
                                    <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60">
                                        <h2 class="font-semibold text-gray-800 dark:text-gray-100">Change Log</h2>
                                    </header>
                                    <div class="p-3">
                                        <${AuditTable} data=${auditData.value} pageSignal=${auditPage} onLoad=${loadAudit} />
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
