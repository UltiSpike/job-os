// Chat 会话 + 消息 —— 取代 q.chat_sessions
import { api } from './client.js';

export const chatApi = {
  // sessions
  listSessions:   (qid)            => api.get('/chat-sessions', { question_id: qid }),
  getSession:     (sid)            => api.get(`/chat-sessions/${sid}`),
  createSession:  (body)           => api.post('/chat-sessions', body), // {question_id, title, variant_ref}
  patchSession:   (sid, body)      => api.patch(`/chat-sessions/${sid}`, body),
  deleteSession:  (sid)            => api.delete(`/chat-sessions/${sid}`),
  restoreSession: (snapshot)       => api.post('/chat-sessions/restore', snapshot),

  // messages (走 session 子路径或扁平 endpoint 都可以；这里走扁平)
  listMessages:   (sid)            => api.get('/chat-messages', { session_id: sid }),
  addMessage:     (sid, role, content) => api.post('/chat-messages', { session_id: sid, role, content }),
  deleteMessage:  (mid)            => api.delete(`/chat-messages/${mid}`),
};
