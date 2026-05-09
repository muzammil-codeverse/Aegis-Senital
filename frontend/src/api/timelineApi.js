import { normalizeItemResponse, request } from './client'

export async function getTimeline(trackId) {
  return normalizeItemResponse(await request({
    url: `/api/timeline/${encodeURIComponent(trackId)}`,
    method: 'GET',
  }))
}
