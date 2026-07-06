import client from './client'

export async function extractTodos(link: string) {
  return client.post('/meeting-todo/extract', { link })
}

export async function generateDoc(title: string, content: string) {
  return client.post('/meeting-todo/generate-doc', { title, content })
}

export async function searchMinutes(keyword: string) {
  return client.post('/meeting-todo/search', { keyword })
}