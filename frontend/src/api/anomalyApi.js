import client from './client';

export const anomalyApi = {
  getRecentEvents: (params = {}) =>
    client.get('/api/anomaly/events', { params }),

  getHealth: () =>
    client.get('/api/anomaly/health'),

  getCameraEvents: (cameraId, params = {}) =>
    client.get(`/api/anomaly/events/${cameraId}`, { params }),

  submitFeedback: (eventId, isFalseAlarm) =>
    client.post(`/api/anomaly/feedback/${eventId}`, { is_false_alarm: isFalseAlarm }),
};
