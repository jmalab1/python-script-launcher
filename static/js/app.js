import { html, render } from '../vendor/standalone-preact.esm.js';
import { useState, useEffect } from '../vendor/standalone-preact.esm.js';
import {
    profiles, workflows, currentPanel, theme, sidebarOpen, PANELS,
    profileHistoryData, workflowHistoryData,
    profileHistoryPage, workflowHistoryPage,
    auditData, auditPage,
    profileTags, workflowTags,
    logData,
} from './state.js';
import {
    loadProfiles, loadWorkflows, loadSchedules, checkAllScripts,
    loadProfileHistory, loadWorkflowHistory,
    loadAudit, loadLogs, pollLogs,
} from './api.js';
import { Sidebar, MobileHeader } from './components/Sidebar.js';
import { ProfileList } from './components/ProfileList.js';
import { ProfileModal } from './components/ProfileModal.js';
import { WorkflowList } from './components/WorkflowList.js';
import { WorkflowModal } from './components/WorkflowModal.js';
import { SchedulesList } from './components/SchedulesList.js';
import { ScheduleModal } from './components/ScheduleModal.js';
import { HistoryTable } from './components/HistoryTable.js';
import { AuditTable } from './components/AuditTable.js';
import { LogViewer } from './components/LogViewer.js';
import { RunModal } from './components/RunModal.js';
import { TagManager } from './components/TagManager.js';

function App() {
    const [initialized, setInitialized] = useState(false);
    const [profileTimer, setProfileTimer] = useState(null);
    const [workflowTimer, setWorkflowTimer] = useState(null);
    const [logTimer, setLogTimer] = useState(null);
    const [scheduleTimer, setScheduleTimer] = useState(null);

    const [runOpen, setRunOpen] = useState(false);
    const [runId, setRunId] = useState(null);
    const [runTitle, setRunTitle] = useState('Run Output');
    const [runType, setRunType] = useState(null);

    const [profileOpen, setProfileOpen] = useState(false);
    const [editingProfile, setEditingProfile] = useState(null);

    const [workflowOpen, setWorkflowOpen] = useState(false);
    const [editingWorkflow, setEditingWorkflow] = useState(null);

    const [scheduleOpen, setScheduleOpen] = useState(false);
    const [editingSchedule, setEditingSchedule] = useState(null);

    const [tagManagerOpen, setTagManagerOpen] = useState(false);
    const [tagManagerType, setTagManagerType] = useState('profiles');

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
            await Promise.all([loadProfiles(), loadWorkflows(), loadSchedules(), loadProfileHistory()]);
            await checkAllScripts();
            setInitialized(true);
        }
        init();
    }, []);

    useEffect(() => {
        if (!initialized) return;

        if (profileTimer) clearInterval(profileTimer);
        if (workflowTimer) clearInterval(workflowTimer);
        if (logTimer) clearInterval(logTimer);
        if (scheduleTimer) clearInterval(scheduleTimer);

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
        if (currentPanel.value === 'schedules') {
            loadSchedules();
            const t = setInterval(loadSchedules, 5000);
            setScheduleTimer(t);
        }
        if (currentPanel.value === 'audit') {
            loadAudit();
        }
        if (currentPanel.value === 'logs') {
            loadLogs();
            const t = setInterval(pollLogs, 2000);
            setLogTimer(t);
        }

        return () => {
            if (profileTimer) clearInterval(profileTimer);
            if (workflowTimer) clearInterval(workflowTimer);
            if (logTimer) clearInterval(logTimer);
            if (scheduleTimer) clearInterval(scheduleTimer);
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

    function openNewScheduleModal() {
        setEditingSchedule(null);
        setScheduleOpen(true);
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
                    <div class="flex flex-col px-4 sm:px-6 lg:px-8 py-6 w-full h-full overflow-hidden">

                        ${currentPanel.value === 'profiles' ? html`
                            <div id="panel-profiles" class="panel flex flex-col flex-1 min-h-0">
                                <div class="flex items-center justify-between mb-6 shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Profiles</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Reusable script presets — point one at a Python script, add its arguments, and run it anytime.</p>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <button onClick=${() => { setTagManagerType('profiles'); setTagManagerOpen(true); }}
                                            class="bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm font-medium px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700/60 transition inline-flex items-center gap-1.5">
                                            <svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/></svg>
                                            Tags
                                        </button>
                                        <button onClick=${openNewProfileModal}
                                            class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                            New Profile
                                        </button>
                                    </div>
                                </div>
                                <div class="grid grid-cols-1 xl:grid-cols-5 gap-6 flex-1 min-h-0 overflow-y-auto xl:overflow-y-visible">
                                    <div class="xl:col-span-2 xl:overflow-y-auto xl:pr-1">
                                        <${ProfileList} onEdit=${(p) => { setEditingProfile(p); setProfileOpen(true); }} onRun=${handleRunStarted} />
                                    </div>
                                    <div class="xl:col-span-3 xl:overflow-y-auto xl:pr-1">
                                        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60 flex flex-col xl:h-full">
                                            <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60 shrink-0">
                                                <h2 class="font-semibold text-gray-800 dark:text-gray-100">Profile Run History</h2>
                                            </header>
                                            <div class="p-3 flex-1 min-h-0 overflow-hidden">
                                                <${HistoryTable} data=${profileHistoryData.value} pageSignal=${profileHistoryPage} onLoad=${loadProfileHistory} type="profile" onOpenRun=${openRunModal} />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                        ${currentPanel.value === 'workflows' ? html`
                            <div id="panel-workflows" class="panel flex flex-col flex-1 min-h-0">
                                <div class="flex items-center justify-between mb-6 shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Workflows</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Chain profiles into ordered steps or parallel groups and run them all with a single click.</p>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <button onClick=${() => { setTagManagerType('workflows'); setTagManagerOpen(true); }}
                                            class="bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm font-medium px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700/60 transition inline-flex items-center gap-1.5">
                                            <svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z"/><path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6z"/></svg>
                                            Tags
                                        </button>
                                        <button onClick=${openNewWorkflowModal}
                                            class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                            New Workflow
                                        </button>
                                    </div>
                                </div>
                                <div class="grid grid-cols-1 xl:grid-cols-5 gap-6 flex-1 min-h-0 overflow-y-auto xl:overflow-y-visible">
                                    <div class="xl:col-span-2 xl:overflow-y-auto xl:pr-1">
                                        <${WorkflowList} onEdit=${(w) => { setEditingWorkflow(w); setWorkflowOpen(true); }} onRun=${handleRunStarted} />
                                    </div>
                                    <div class="xl:col-span-3 xl:overflow-y-auto xl:pr-1">
                                        <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60 flex flex-col xl:h-full">
                                            <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60 shrink-0">
                                                <h2 class="font-semibold text-gray-800 dark:text-gray-100">Run History</h2>
                                            </header>
                                            <div class="p-3 flex-1 min-h-0 overflow-hidden">
                                                <${HistoryTable} data=${workflowHistoryData.value} pageSignal=${workflowHistoryPage} onLoad=${loadWorkflowHistory} type="workflow" onOpenRun=${openRunModal} />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                        ${currentPanel.value === 'schedules' ? html`
                            <div id="panel-schedules" class="panel flex flex-col flex-1 min-h-0">
                                <div class="flex items-center justify-between mb-6 shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Schedules</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Run profiles and workflows automatically on a cron-like schedule — every hour, daily at noon, weekdays at 08:00, or any cron expression.</p>
                                    </div>
                                    <button onClick=${openNewScheduleModal}
                                        class="bg-gray-900 text-gray-100 hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-800 dark:hover:bg-white text-sm font-medium px-3 py-2 rounded-lg inline-flex items-center gap-1.5 transition">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>
                                        New Schedule
                                    </button>
                                </div>
                                <div class="flex-1 min-h-0 overflow-y-auto">
                                    <${SchedulesList} onEdit=${(s) => { setEditingSchedule(s); setScheduleOpen(true); }} />
                                </div>
                            </div>
                        ` : ''}

                        ${currentPanel.value === 'audit' ? html`
                            <div id="panel-audit" class="panel flex flex-col flex-1 min-h-0">
                                <div class="flex items-center justify-between mb-6 shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Audit</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Who did what, when — every profile and workflow addition, edit, deletion, and reorder, with before/after snapshots.</p>
                                    </div>
                                </div>
                                <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60 flex flex-col flex-1 min-h-0">
                                    <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60 shrink-0">
                                        <h2 class="font-semibold text-gray-800 dark:text-gray-100">Change Log</h2>
                                    </header>
                                    <div class="p-3 flex-1 min-h-0 overflow-hidden">
                                        <${AuditTable} data=${auditData.value} pageSignal=${auditPage} onLoad=${loadAudit} />
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                        ${currentPanel.value === 'logs' ? html`
                            <div id="panel-logs" class="panel flex flex-col flex-1 min-h-0">
                                <div class="flex items-center justify-between mb-6 shrink-0">
                                    <div class="min-w-0">
                                        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Server Logs</h1>
                                        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Live view of Tiller's own log file — new lines are tailed every 2 seconds.</p>
                                    </div>
                                </div>
                                <div class="bg-white dark:bg-gray-800 shadow-xs rounded-xl border border-gray-200 dark:border-gray-700/60 flex flex-col flex-1 min-h-0">
                                    <header class="px-5 py-4 border-b border-gray-100 dark:border-gray-700/60 shrink-0">
                                        <h2 class="font-semibold text-gray-800 dark:text-gray-100">server.log</h2>
                                    </header>
                                    <div class="p-3 flex-1 min-h-0 overflow-hidden">
                                        <${LogViewer} data=${logData.value} />
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                    </div>
                </div>
            </div>

            <${ProfileModal} isOpen=${profileOpen} onClose=${() => setProfileOpen(false)} profile=${editingProfile} />
            <${WorkflowModal} isOpen=${workflowOpen} onClose=${() => setWorkflowOpen(false)} workflow=${editingWorkflow} />
            <${ScheduleModal} isOpen=${scheduleOpen} onClose=${() => setScheduleOpen(false)} schedule=${editingSchedule} />
            <${RunModal} isOpen=${runOpen} onClose=${() => setRunOpen(false)} runId=${runId} title=${runTitle} runType=${runType} />
            <${TagManager}
                isOpen=${tagManagerOpen}
                onClose=${() => setTagManagerOpen(false)}
                tags=${tagManagerType === 'profiles' ? profileTags.value : workflowTags.value}
                tagsSignal=${tagManagerType === 'profiles' ? profileTags : workflowTags}
                items=${tagManagerType === 'profiles' ? profiles.value : workflows.value}
                getTag=${(item) => item.group || ''}
            />
        </div>
    `;
}

render(html`<${App} />`, document.getElementById('app'));
