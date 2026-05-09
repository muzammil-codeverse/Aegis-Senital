/**
 * useIdentities — polling hook for identity profiles, enrollments, and match history.
 *
 * Provides create, update, archive, and face-upload operations that
 * automatically refresh the identity list on success.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getIdentities,
  createIdentity,
  updateIdentity,
  deleteIdentity,
  getIdentityEnrollments,
  getIdentityMatches,
  enrollFace,
} from '../api/identityApi.js';

const POLL_MS = 10000;

export function useIdentities(pollInterval = POLL_MS) {
  const [identities, setIdentities] = useState([]);
  const [selectedIdentity, setSelectedIdentity] = useState(null);
  const [enrollments, setEnrollments] = useState([]);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const fetchIdentities = useCallback(async () => {
    try {
      const res = await getIdentities();
      if (res.status !== 'error') {
        setIdentities(res.items || []);
        setError(null);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIdentities();
    timerRef.current = setInterval(fetchIdentities, pollInterval);
    return () => clearInterval(timerRef.current);
  }, [fetchIdentities, pollInterval]);

  const selectIdentity = useCallback(async (identity) => {
    setSelectedIdentity(identity);
    if (!identity) return;
    const [enr, mat] = await Promise.all([
      getIdentityEnrollments(identity.identity_id),
      getIdentityMatches(identity.identity_id),
    ]);
    setEnrollments(enr.items || []);
    setMatches(mat.items || []);
  }, []);

  const create = useCallback(async (payload) => {
    const res = await createIdentity(payload);
    if (res.status === 'ok') await fetchIdentities();
    return res;
  }, [fetchIdentities]);

  const update = useCallback(async (identityId, payload) => {
    const res = await updateIdentity(identityId, payload);
    if (res.status === 'ok') await fetchIdentities();
    return res;
  }, [fetchIdentities]);

  const archive = useCallback(async (identityId) => {
    const res = await deleteIdentity(identityId);
    if (res.status === 'ok') {
      await fetchIdentities();
      if (selectedIdentity?.identity_id === identityId) setSelectedIdentity(null);
    }
    return res;
  }, [fetchIdentities, selectedIdentity]);

  const uploadFace = useCallback(async (identityId, file, metadata = {}) => {
    const res = await enrollFace(identityId, file, metadata);
    if (res.status === 'ok' && selectedIdentity?.identity_id === identityId) {
      const enr = await getIdentityEnrollments(identityId);
      setEnrollments(enr.items || []);
    }
    return res;
  }, [selectedIdentity]);

  return {
    identities,
    selectedIdentity,
    enrollments,
    matches,
    loading,
    error,
    refresh: fetchIdentities,
    selectIdentity,
    create,
    update,
    archive,
    uploadFace,
  };
}
