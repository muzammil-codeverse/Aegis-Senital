import { request } from './client';

export const anomalyApi = {
  getRecentEvents: (params = {}) =>
    request({ url: '/api/anomaly/events', method: 'GET', params }),

  getHealth: () =>
    request({ url: '/api/anomaly/health', method: 'GET' }),

  getCameraEvents: (cameraId, params = {}) =>
    request({
      url: `/api/anomaly/events/${encodeURIComponent(cameraId)}`,
      method: 'GET',
      params,
    }),

  submitFeedback: (eventId, isFalseAlarm) =>
    request({
      url: `/api/anomaly/feedback/${encodeURIComponent(eventId)}`,
      method: 'POST',
      data: { is_false_alarm: isFalseAlarm },
    }),
};
