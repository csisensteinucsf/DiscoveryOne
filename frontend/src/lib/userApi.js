import { apiFetch } from './apiClient.js'

export function saveUserRequest(apiBase, { editingId = null, payload }) {
  const url = editingId ? `${apiBase}/users/${editingId}` : `${apiBase}/users`
  const method = editingId ? 'PATCH' : 'POST'
  return apiFetch(url, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, {
    errorMessage: editingId ? 'Unable to update user.' : 'Unable to create user.',
  })
}