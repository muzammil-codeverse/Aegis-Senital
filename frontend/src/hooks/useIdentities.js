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
  getIdentityEnrollmentProfiles,
  getIdentityHealth,
  getIdentityRuntimeOverview,
  getIdentityMatches,
  getGlobalIdentityRegistry,
  enrollFace,
  enrollIdentity,
  deleteIdentityEnrollmentProfile,
} from '../api/identityApi.js';

const POLL_MS = 10000;

export function useIdentities(pollInterval = POLL_MS) {
  const [identities, setIdentities] = useState([]);
  const [selectedIdentity, setSelectedIdentity] = useState(null);
  const [enrollments, setEnrollments] = useState([]);
  const [enrollmentProfiles, setEnrollmentProfiles] = useState([]);
  const [matches, setMatches] = useState([]);
  const [identityHealth, setIdentityHealth] = useState(null);
  const [identityMetrics, setIdentityMetrics] = useState(null);
  const [globalIdentities, setGlobalIdentities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const fetchIdentities = useCallback(async () => {
    try {
      const [res, healthRes, registryRes, overviewRes] = await Promise.all([
        getIdentities(),
        getIdentityHealth(),
        getGlobalIdentityRegistry({ limit: 100 }),
        getIdentityRuntimeOverview(),
      ]);
      if (res.status !== 'error') {
        setIdentities(res.items || []);
      }
      if (healthRes.status !== 'error') setIdentityHealth(healthRes.item || null);
      if (registryRes.status !== 'error') setGlobalIdentities(registryRes.items || []);
      if (overviewRes.status !== 'error') setIdentityMetrics(overviewRes.item?.metrics || null);
      setError(null);
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
    if (!identity) {
      setEnrollments([]);
      setMatches([]);
      setEnrollmentProfiles([]);
      return;
    }
    const [enr, mat, profiles] = await Promise.all([
      getIdentityEnrollments(identity.identity_id),
      getIdentityMatches(identity.identity_id),
      getIdentityEnrollmentProfiles({ identity_id: identity.identity_id }),
    ]);
    setEnrollments(enr.items || []);
    setMatches(mat.items || []);
    setEnrollmentProfiles(profiles.items || []);
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
      const [enr, profiles] = await Promise.all([
        getIdentityEnrollments(identityId),
        getIdentityEnrollmentProfiles({ identity_id: identityId }),
      ]);
      setEnrollments(enr.items || []);
      setEnrollmentProfiles(profiles.items || []);
    }
    return res;
  }, [selectedIdentity]);

  const batchEnroll = useCallback(async (files, payload = {}) => {
    const res = await enrollIdentity(files, payload);
    if (res.status === 'ok') {
      await fetchIdentities();
      const resolvedIdentityId = payload.identity_id || res.identity_id;
      if (resolvedIdentityId) {
        const [enr, profiles] = await Promise.all([
          getIdentityEnrollments(resolvedIdentityId),
          getIdentityEnrollmentProfiles({ identity_id: resolvedIdentityId }),
        ]);
        setEnrollments(enr.items || []);
        setEnrollmentProfiles(profiles.items || []);
      }
    }
    return res;
  }, [fetchIdentities]);

  const deleteEnrollment = useCallback(async (enrollmentId) => {
    const res = await deleteIdentityEnrollmentProfile(enrollmentId);
    if (res.status === 'ok' && selectedIdentity?.identity_id) {
      const profiles = await getIdentityEnrollmentProfiles({ identity_id: selectedIdentity.identity_id });
      setEnrollmentProfiles(profiles.items || []);
    }
    return res;
  }, [selectedIdentity]);

  return {
    identities,
    selectedIdentity,
    enrollments,
    enrollmentProfiles,
    matches,
    identityHealth,
    identityMetrics,
    globalIdentities,
    loading,
    error,
    refresh: fetchIdentities,
    selectIdentity,
    create,
    update,
    archive,
    uploadFace,
    batchEnroll,
    deleteEnrollment,
  };
}
