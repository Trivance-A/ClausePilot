import { buildUrl, authHeaders, ApiError } from '@/lib/api';
import type { SseEvent } from '@/types/api';

/**
 * fetch 기반 SSE 클라이언트 (EventSource는 POST·Authorization 헤더 미지원).
 * text/event-stream 을 event/data 블록 단위로 파싱해 onEvent 콜백으로 전달한다.
 */
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(buildUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let code = `HTTP_${res.status}`; let message = res.statusText;
    try { const j = await res.json(); code = j?.error?.code ?? code; message = j?.error?.message ?? message; } catch { /* ignore */ }
    throw new ApiError(res.status, code, message);
  }
  if (!res.body) throw new Error('스트림 응답이 없습니다');

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const flushBlock = (block: string) => {
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    try {
      onEvent({ event, data: JSON.parse(dataLines.join('\n')) } as SseEvent);
    } catch {
      onEvent({ event: 'token', data: { text: dataLines.join('\n') } });
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, '\n');
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (block.trim()) flushBlock(block);
    }
  }
  if (buffer.trim()) flushBlock(buffer);
}
