import apiClient from './client'

export interface FeedbackPayload {
  message_id: string
  type: 'positive' | 'negative'
  reason?: string
  comment?: string
}

export async function submitFeedback(feedback: FeedbackPayload): Promise<void> {
  await apiClient.post('/api/feedback', feedback)
}

export const feedbackApi = {
  submitFeedback,
}
