import { html } from '../../vendor/standalone-preact.esm.js';
import { currentPanel, theme, sidebarOpen } from '../state.js';

function applyTheme(t) {
    const root = document.documentElement;
    if (t === 'light') root.classList.remove('dark');
    else root.classList.add('dark');
    localStorage.setItem('theme', t);
    updateThemeIcons(t);
}

function updateThemeIcons(t) {
    const isDark = t === 'dark';
    const ids = [
        ['theme-icon-dark', !isDark], ['theme-icon-light', isDark],
        ['mob-theme-icon-dark', !isDark], ['mob-theme-icon-light', isDark],
    ];
    ids.forEach(([id, hidden]) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('hidden', hidden);
    });
    const label = document.getElementById('theme-label');
    if (label) label.textContent = isDark ? 'Light Mode' : 'Dark Mode';
}

function toggleTheme() {
    const next = theme.value === 'dark' ? 'light' : 'dark';
    theme.value = next;
    applyTheme(next);
}

function showPanel(name) {
    currentPanel.value = name;
    localStorage.setItem('panel', name);
    const hash = `#/${name}`;
    if (location.hash !== hash) history.replaceState(null, '', hash);
    sidebarOpen.value = false;
}

export function Sidebar() {
    const isDark = theme.value === 'dark';

    return html`
        <aside class="hidden md:flex flex-col w-48 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700/60 shrink-0">
            <div class="flex items-center gap-2.5 px-5 py-4 border-b border-gray-200 dark:border-gray-700/60">
                <svg class="w-7 h-7 text-violet-500 shrink-0" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M31.956 14.8C31.372 6.92 25.08.628 17.2.044V5.76a9.04 9.04 0 0 0 9.04 9.04h5.716ZM14.8 26.24v5.716C6.92 31.372.63 25.08.044 17.2H5.76a9.04 9.04 0 0 1 9.04 9.04Zm11.44-9.04h5.716c-.584 7.88-6.876 14.172-14.756 14.756V26.24a9.04 9.04 0 0 1 9.04-9.04ZM.044 14.8C.63 6.92 6.92.628 14.8.044V5.76a9.04 9.04 0 0 1-9.04 9.04H.044Z" fill="currentColor"/></svg>
                <span class="text-[15px] font-bold text-gray-800 dark:text-gray-100 tracking-tight">Tiller</span>
            </div>
            <nav class="flex-1 px-3 py-3 space-y-0.5">
                <button onClick=${() => showPanel('profiles')}
                    class="nav-btn ${currentPanel.value === 'profiles' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
                    Profiles
                </button>
                <button onClick=${() => showPanel('workflows')}
                    class="nav-btn ${currentPanel.value === 'workflows' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 0 0-3.7-3.7 48.678 48.678 0 0 0-7.324 0 4.006 4.006 0 0 0-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 0 0 3.7 3.7 48.656 48.656 0 0 0 7.324 0 4.006 4.006 0 0 0 3.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3-3 3"/></svg>
                    Workflows
                </button>
                <button onClick=${() => showPanel('schedules')}
                    class="nav-btn ${currentPanel.value === 'schedules' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    Schedules
                </button>
                <button onClick=${() => showPanel('audit')}
                    class="nav-btn ${currentPanel.value === 'audit' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"/></svg>
                    Audit
                </button>
                <button onClick=${() => showPanel('logs')}
                    class="nav-btn ${currentPanel.value === 'logs' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></svg>
                    Logs
                </button>
            </nav>
            <div class="px-3 py-3 border-t border-gray-200 dark:border-gray-700/60">
                <button onClick=${toggleTheme}
                    class="nav-btn w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg id="theme-icon-dark" class="w-4 h-4 shrink-0 ${isDark ? '' : 'hidden'}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"/></svg>
                    <svg id="theme-icon-light" class="w-4 h-4 shrink-0 ${isDark ? 'hidden' : ''}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"/></svg>
                    <span id="theme-label">${isDark ? 'Light Mode' : 'Dark Mode'}</span>
                </button>
            </div>
        </aside>
    `;
}

export function MobileHeader() {
    const isDark = theme.value === 'dark';

    return html`
        <div id="sidebar-overlay" class="fixed inset-0 bg-black/50 z-40 md:hidden ${sidebarOpen.value ? '' : 'hidden'}"
            onClick=${() => { sidebarOpen.value = false; }}></div>

        <header class="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700/60 md:hidden shrink-0">
            <button onClick=${() => { sidebarOpen.value = !sidebarOpen.value; }}
                class="p-1.5 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>
            </button>
            <svg class="w-6 h-6 text-violet-500 shrink-0" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M31.956 14.8C31.372 6.92 25.08.628 17.2.044V5.76a9.04 9.04 0 0 0 9.04 9.04h5.716ZM14.8 26.24v5.716C6.92 31.372.63 25.08.044 17.2H5.76a9.04 9.04 0 0 1 9.04 9.04Zm11.44-9.04h5.716c-.584 7.88-6.876 14.172-14.756 14.756V26.24a9.04 9.04 0 0 1 9.04-9.04ZM.044 14.8C.63 6.92 6.92.628 14.8.044V5.76a9.04 9.04 0 0 1-9.04 9.04H.044Z" fill="currentColor"/></svg>
            <span class="text-sm font-bold text-gray-800 dark:text-gray-100">Tiller</span>
            <div class="flex-1"></div>
            <button onClick=${toggleTheme}
                class="p-1.5 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700/50">
                <svg id="mob-theme-icon-dark" class="w-5 h-5 ${isDark ? '' : 'hidden'}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"/></svg>
                <svg id="mob-theme-icon-light" class="w-5 h-5 ${isDark ? 'hidden' : ''}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"/></svg>
            </button>
            <div class="flex gap-1">
                <button onClick=${() => showPanel('profiles')}
                    class="mob-nav px-2.5 py-1 rounded-md text-xs font-medium ${currentPanel.value === 'profiles' ? 'text-violet-500 bg-violet-500/10' : 'text-gray-500 dark:text-gray-400'}">Profiles</button>
                <button onClick=${() => showPanel('workflows')}
                    class="mob-nav px-2.5 py-1 rounded-md text-xs font-medium ${currentPanel.value === 'workflows' ? 'text-violet-500 bg-violet-500/10' : 'text-gray-500 dark:text-gray-400'}">Workflows</button>
                <button onClick=${() => showPanel('schedules')}
                    class="mob-nav px-2.5 py-1 rounded-md text-xs font-medium ${currentPanel.value === 'schedules' ? 'text-violet-500 bg-violet-500/10' : 'text-gray-500 dark:text-gray-400'}">Schedules</button>
                <button onClick=${() => showPanel('audit')}
                    class="mob-nav px-2.5 py-1 rounded-md text-xs font-medium ${currentPanel.value === 'audit' ? 'text-violet-500 bg-violet-500/10' : 'text-gray-500 dark:text-gray-400'}">Audit</button>
                <button onClick=${() => showPanel('logs')}
                    class="mob-nav px-2.5 py-1 rounded-md text-xs font-medium ${currentPanel.value === 'logs' ? 'text-violet-500 bg-violet-500/10' : 'text-gray-500 dark:text-gray-400'}">Logs</button>
            </div>
        </header>

        <aside class="md:hidden ${sidebarOpen.value ? 'flex' : 'hidden'} fixed inset-y-0 left-0 z-50 flex-col w-48 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700/60">
            <div class="flex items-center gap-2.5 px-5 py-4 border-b border-gray-200 dark:border-gray-700/60">
                <svg class="w-7 h-7 text-violet-500 shrink-0" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M31.956 14.8C31.372 6.92 25.08.628 17.2.044V5.76a9.04 9.04 0 0 0 9.04 9.04h5.716ZM14.8 26.24v5.716C6.92 31.372.63 25.08.044 17.2H5.76a9.04 9.04 0 0 1 9.04 9.04Zm11.44-9.04h5.716c-.584 7.88-6.876 14.172-14.756 14.756V26.24a9.04 9.04 0 0 1 9.04-9.04ZM.044 14.8C.63 6.92 6.92.628 14.8.044V5.76a9.04 9.04 0 0 1-9.04 9.04H.044Z" fill="currentColor"/></svg>
                <span class="text-[15px] font-bold text-gray-800 dark:text-gray-100 tracking-tight">Tiller</span>
            </div>
            <nav class="flex-1 px-3 py-3 space-y-0.5">
                <button onClick=${() => showPanel('profiles')}
                    class="nav-btn ${currentPanel.value === 'profiles' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"/></svg>
                    Profiles
                </button>
                <button onClick=${() => showPanel('workflows')}
                    class="nav-btn ${currentPanel.value === 'workflows' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 0 0-3.7-3.7 48.678 48.678 0 0 0-7.324 0 4.006 4.006 0 0 0-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 0 0 3.7 3.7 48.656 48.656 0 0 0 7.324 0 4.006 4.006 0 0 0 3.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3-3 3"/></svg>
                    Workflows
                </button>
                <button onClick=${() => showPanel('schedules')}
                    class="nav-btn ${currentPanel.value === 'schedules' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    Schedules
                </button>
                <button onClick=${() => showPanel('audit')}
                    class="nav-btn ${currentPanel.value === 'audit' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"/></svg>
                    Audit
                </button>
                <button onClick=${() => showPanel('logs')}
                    class="nav-btn ${currentPanel.value === 'logs' ? 'active' : ''} w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"/></svg>
                    Logs
                </button>
            </nav>
            <div class="px-3 py-3 border-t border-gray-200 dark:border-gray-700/60">
                <button onClick=${toggleTheme}
                    class="nav-btn w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium">
                    <svg class="w-4 h-4 shrink-0 ${isDark ? '' : 'hidden'}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"/></svg>
                    <svg class="w-4 h-4 shrink-0 ${isDark ? 'hidden' : ''}" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"/></svg>
                    <span>${isDark ? 'Light Mode' : 'Dark Mode'}</span>
                </button>
            </div>
        </aside>
    `;
}
