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
