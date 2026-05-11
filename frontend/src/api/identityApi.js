/**
 * identityApi.js — Phase 20 API client for identity, watchlist, and model registry.
 *
 * All functions return structured { items, count, status } or { item, status, detail }
 * responses consistent with the normalisation helpers in client.js.
 */
import { apiClient, normalizeListResponse, normalizeItemResponse } from './client.js';

// ---------------------------------------------------------------------------
// Identity endpoints
// ---------------------------------------------------------------------------

export async function getIdentities(params = {}) {
  try {
    const res = await apiClient.get('/api/identities', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error', detail: e.message };
  }
}

export async function createIdentity(payload) {
  try {
    const res = await apiClient.post('/api/identities', payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function getIdentity(identityId) {
  try {
    const res = await apiClient.get(`/api/identities/${identityId}`);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function updateIdentity(identityId, payload) {
  try {
    const res = await apiClient.patch(`/api/identities/${identityId}`, payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function deleteIdentity(identityId) {
  try {
    const res = await apiClient.delete(`/api/identities/${identityId}`);
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

/**
 * Upload a face image for a specific identity.
 * Uses multipart/form-data; the FormData object is constructed here.
 */
export async function enrollFace(identityId, file, metadata = {}) {
  try {
    const form = new FormData();
    form.append('file', file);
    if (metadata.display_name) form.append('display_name', metadata.display_name);
    const res = await apiClient.post(
      `/api/identities/${identityId}/enroll-face`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

export async function enrollIdentity(files, payload = {}) {
  try {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    if (payload.identity_id) form.append('identity_id', payload.identity_id);
    if (payload.display_name) form.append('display_name', payload.display_name);
    if (payload.metadata) form.append('metadata_json', JSON.stringify(payload.metadata));
    const res = await apiClient.post('/api/identity/enroll', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

export async function getIdentityEnrollments(identityId) {
  try {
    const res = await apiClient.get(`/api/identities/${identityId}/enrollments`);
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

export async function getIdentityMatches(identityId, limit = 100) {
  try {
    const res = await apiClient.get(`/api/identities/${identityId}/matches`, {
      params: { limit },
    });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

export async function getIdentityEnrollmentProfiles(params = {}) {
  try {
    const res = await apiClient.get('/api/identity/enrollments', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error', detail: e.message };
  }
}

export async function deleteIdentityEnrollmentProfile(enrollmentId) {
  try {
    const res = await apiClient.delete(`/api/identity/enrollments/${enrollmentId}`);
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

export async function getIdentityHealth() {
  try {
    const res = await apiClient.get('/api/identity/health');
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function getIdentityRuntimeOverview() {
  try {
    const res = await apiClient.get('/health');
    return { item: res.data, status: 'ok' };
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function getGlobalIdentityRegistry(params = {}) {
  try {
    const res = await apiClient.get('/api/identity/registry', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error', detail: e.message };
  }
}

export async function getIdentityCandidates(params = {}) {
  try {
    const res = await apiClient.get('/api/identity/candidates', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error', detail: e.message };
  }
}

export async function acceptIdentityCandidate(candidateId, payload = {}) {
  try {
    const res = await apiClient.post(`/api/identity/candidates/${candidateId}/accept`, payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function rejectIdentityCandidate(candidateId, payload = {}) {
  try {
    const res = await apiClient.post(`/api/identity/candidates/${candidateId}/reject`, payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function escalateIdentityCandidate(candidateId, payload = {}) {
  try {
    const res = await apiClient.post(`/api/identity/candidates/${candidateId}/escalate`, payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

// ---------------------------------------------------------------------------
// Watchlist endpoints
// ---------------------------------------------------------------------------

export async function getWatchlist(params = {}) {
  try {
    const res = await apiClient.get('/api/watchlist', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

export async function addWatchlistEntry(payload) {
  try {
    const res = await apiClient.post('/api/watchlist', payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}

export async function removeWatchlistEntry(watchlistId) {
  try {
    const res = await apiClient.delete(`/api/watchlist/${watchlistId}`);
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

export async function getIdentityWatchlist(identityId) {
  try {
    const res = await apiClient.get(`/api/watchlist/identity/${identityId}`);
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

// ---------------------------------------------------------------------------
// Model registry endpoints
// ---------------------------------------------------------------------------

export async function getModels(params = {}) {
  try {
    const res = await apiClient.get('/api/models', { params });
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

export async function getModel(modelId) {
  try {
    const res = await apiClient.get(`/api/models/${modelId}`);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error' };
  }
}

export async function getModelHealth() {
  try {
    const res = await apiClient.get('/api/models/health');
    return normalizeListResponse(res.data);
  } catch (e) {
    return { items: [], count: 0, status: 'error' };
  }
}

export async function reloadModels() {
  try {
    const res = await apiClient.post('/api/models/reload');
    return res.data;
  } catch (e) {
    return { status: 'error', detail: e.message };
  }
}

export async function updateModel(modelId, payload) {
  try {
    const res = await apiClient.patch(`/api/models/${modelId}`, payload);
    return normalizeItemResponse(res.data);
  } catch (e) {
    return { item: null, status: 'error', detail: e.message };
  }
}
