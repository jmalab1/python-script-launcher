import {
    profiles, workflows, scriptStatusCache,
    profileHistoryPage, workflowHistoryPage,
    profileHistoryData, workflowHistoryData,
    auditPage, auditData, auditAction, auditEntity,
} from './state.js';

async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return res.json();
}

export async function loadProfiles() {
    profiles.value = await api('GET', '/api/profiles');
}

export async function loadWorkflows() {
    workflows.value = await api('GET', '/api/workflows');
}

export async function checkScriptExists(path) {
    if (scriptStatusCache.value[path] !== undefined) return scriptStatusCache.value[path];
    const res = await api('GET', '/api/script_exists?path=' + encodeURIComponent(path));
    scriptStatusCache.value = { ...scriptStatusCache.value, [path]: res.exists };
    return res.exists;
}

export async function checkAllScripts() {
    const paths = profiles.value.filter(p => p.script_path).map(p => p.script_path);
    const results = await Promise.all(paths.map(async path => {
        if (scriptStatusCache.value[path] !== undefined) return [path, scriptStatusCache.value[path]];
        const res = await api('GET', '/api/script_exists?path=' + encodeURIComponent(path));
        return [path, res.exists];
    }));
    scriptStatusCache.value = { ...scriptStatusCache.value, ...Object.fromEntries(results) };
}

export async function saveProfile(data) {
    return api('POST', '/api/profiles', data);
}

export async function deleteProfile(id) {
    return api('DELETE', '/api/profiles/' + id);
}

export async function restoreProfile(id) {
    return api('POST', `/api/profiles/${id}/restore`);
}

export async function permanentDeleteProfile(id) {
    return api('DELETE', `/api/profiles/${id}/permanent`);
}

export async function duplicateProfile(id) {
    return api('POST', `/api/profiles/${id}/duplicate`);
}

export async function saveProfileOrder(ids) {
    return api('POST', '/api/profiles/reorder', { order: ids });
}

export async function saveWorkflow(data) {
    return api('POST', '/api/workflows', data);
}

export async function deleteWorkflow(id) {
    return api('DELETE', '/api/workflows/' + id);
}

export async function restoreWorkflow(id) {
    return api('POST', `/api/workflows/${id}/restore`);
}

export async function permanentDeleteWorkflow(id) {
    return api('DELETE', `/api/workflows/${id}/permanent`);
}

export async function duplicateWorkflow(id) {
    return api('POST', `/api/workflows/${id}/duplicate`);
}

export async function saveWorkflowOrder(ids) {
    return api('POST', '/api/workflows/reorder', { order: ids });
}

export async function runProfile(id, argValues) {
    return api('POST', '/api/run/profile', { profile_id: id, arg_values: argValues });
}

export async function runWorkflow(id) {
    return api('POST', '/api/run/workflow', { workflow_id: id });
}

export async function pollRun(runId) {
    return api('GET', '/api/runs/' + runId);
}

export async function fetchHistoryRun(runId, runType) {
    const url = runType ? `/api/history/${runId}?type=${runType}` : `/api/history/${runId}`;
    return api('GET', url);
}

export async function loadProfileHistory() {
    const data = await api('GET', `/api/history?page=${profileHistoryPage.value}&per_page=15&type=profile`);
    profileHistoryData.value = data;
}

export async function loadWorkflowHistory() {
    const data = await api('GET', `/api/history?page=${workflowHistoryPage.value}&per_page=15&type=workflow`);
    workflowHistoryData.value = data;
}

export async function deleteHistoryEntry(runId) {
    await api('DELETE', '/api/history/' + runId);
    await loadProfileHistory();
    await loadWorkflowHistory();
}

export async function deleteHistoryEntries(ids) {
    await api('POST', '/api/history/bulk', { ids });
    await loadProfileHistory();
    await loadWorkflowHistory();
}

export async function openNativeFileDialog() {
    return api('GET', '/api/filedialog');
}

export async function loadAudit() {
    const params = new URLSearchParams({ page: auditPage.value, per_page: 20 });
    if (auditAction.value) params.set('action', auditAction.value);
    if (auditEntity.value) params.set('entity', auditEntity.value);
    auditData.value = await api('GET', '/api/audit?' + params.toString());
}

export async function fetchAuditDetail(entryId) {
    return api('GET', '/api/audit/' + entryId);
}
