import client from './client'

export async function sendMessage(message: string, conversationId?: string) {
  return client.post('/chat/send', { message, conversation_id: conversationId })
}

export async function listConversations() {
  return client.get('/chat/conversations')
}