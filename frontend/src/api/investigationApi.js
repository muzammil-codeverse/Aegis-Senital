import { request } from './client';

export const investigationApi = {
  reconstructPath: (body) =>
    request({ method: 'POST', url: '/api/investigation/path-reconstruction', data: body }),

  listHypotheses: (params = {}) =>
    request({ method: 'GET', url: '/api/investigation/hypotheses', params }),

  getHypothesis: (hypothesisId) =>
    request({ method: 'GET', url: `/api/investigation/hypotheses/${hypothesisId}` }),

  acceptHypothesis: (hypothesisId) =>
    request({ method: 'POST', url: `/api/investigation/hypotheses/${hypothesisId}/accept` }),

  rejectHypothesis: (hypothesisId) =>
    request({ method: 'POST', url: `/api/investigation/hypotheses/${hypothesisId}/reject` }),

  markInconclusive: (hypothesisId) =>
    request({ method: 'POST', url: `/api/investigation/hypotheses/${hypothesisId}/inconclusive` }),

  getCaseTimeline: (caseId) =>
    request({ method: 'GET', url: `/api/investigation/cases/${caseId}/timeline` }),

  getCameraGraph: () =>
    request({ method: 'GET', url: '/api/investigation/cameras/graph' }),
};
