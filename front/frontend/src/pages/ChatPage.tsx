import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { MessageSquare, Plus, SendHorizonal, Square } from 'lucide-react';
import { toast } from 'sonner';
import { useChatMessages, useChatSessions, useCreateChatSession, useMessageFeedback } from '@/api/chat';
import { useRegulations } from '@/api/regulations';
import { streamSSE } from '@/lib/sse';
import { errorMessage } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Empty } from '@/components/ui/empty';
import { MessageBubble, type StreamingState } from '@/components/chat/MessageBubble';
import { EvidenceModal } from '@/components/chat/EvidenceModal';
import type { ChatMessage, Citation, Suggestion } from '@/types/api';

const NOT_FOUND_TEXT = '등록된 규정에서 해당 내용을 찾을 수 없습니다.';

export function ChatPage() {
  const { sid } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: sessions } = useChatSessions();
  const { data: history } = useChatMessages(sid);
  const { data: regs } = useRegulations();
  const createSession = useCreateChatSession();
  const feedback = useMessageFeedback();

  const [scope, setScope] = useState<string>('ALL');
  const [input, setInput] = useState('');
  const [local, setLocal] = useState<ChatMessage[]>([]);           // 서버 반영 전 낙관적 메시지
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setLocal([]); setStreaming(null); abortRef.current?.abort(); }, [sid]);
  const messages = useMemo(() => {
    const server = history?.items ?? [];
    const ids = new Set(server.map((m) => m.id));
    return [...server, ...local.filter((m) => !ids.has(m.id))]; // 서버 반영 후 중복 제거
  }, [history, local]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ block: 'end' }); }, [messages, streaming?.content]);

  const ensureSession = async (): Promise<string> => {
    if (sid) return sid;
    const regulation_ids = scope === 'ALL' ? [] : [scope];
    const r = await createSession.mutateAsync({ regulation_ids });
    navigate(`/chat/${r.session_id}`, { replace: true });
    return r.session_id;
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || streaming) return;
    setInput('');
    let sessionId: string;
    try { sessionId = await ensureSession(); } catch (e) { toast.error(errorMessage(e)); return; }

    const tempUser: ChatMessage = { id: `tmp-u-${Date.now()}`, role: 'user', content };
    const tempBot: ChatMessage = { id: `tmp-a-${Date.now()}`, role: 'assistant', content: '' };
    setLocal((l) => [...l, tempUser, tempBot]);
    const st: StreamingState = { content: '', citations: [], stage: 'rewrite', done: false };
    setStreaming({ ...st });
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      await streamSSE(`/chat/sessions/${sessionId}/messages`, { content, stream: true }, (ev) => {
        if (ev.event === 'status') { st.stage = ev.data.stage; if (ev.data.stage === 'retrieve') st.stage = 'retrieve'; }
        else if (ev.event === 'token') { st.content += ev.data.text; st.stage = 'generate'; }
        else if (ev.event === 'citation') { if (!st.citations.some((c) => c.ref === ev.data.ref)) st.citations.push(ev.data); }
        else if (ev.event === 'done') {
          st.done = true;
          const final: ChatMessage = {
            id: ev.data.message_id, role: 'assistant', answer_status: ev.data.answer_status,
            content: st.content || ev.data.content || (ev.data.answer_status === 'NOT_FOUND' ? NOT_FOUND_TEXT : ''),
            citations: st.citations, suggestions: ev.data.suggestions, latency_ms: ev.data.latency_ms,
          };
          setLocal((l) => l.map((m) => (m.id === tempBot.id ? final : m)));
        } else if (ev.event === 'error') { throw new Error(ev.data.message); }
        setStreaming({ ...st, citations: [...st.citations] });
      }, ac.signal);
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        setLocal((l) => l.map((m) => (m.id === tempBot.id ? { ...m, content: st.content || '(중단됨)', answer_status: 'ERROR' } : m)));
      } else {
        toast.error(errorMessage(e));
        setLocal((l) => l.map((m) => (m.id === tempBot.id ? { ...m, content: `오류: ${errorMessage(e)}`, answer_status: 'ERROR' } : m)));
      }
    } finally {
      setStreaming(null);
      abortRef.current = null;
      qc.invalidateQueries({ queryKey: ['chat-sessions'] });
      // 서버 히스토리로 동기화 후 로컬 메시지 제거
      qc.invalidateQueries({ queryKey: ['chat-messages', sessionId] }).then(() => setLocal([]));
    }
  };

  const onSubmit = (e: FormEvent) => { e.preventDefault(); send(input); };
  const askAgain = (c: Citation) => { setCitation(null); const q = `${c.path.split('>').pop()?.trim() ?? c.path}의 내용을 알려줘`; setInput(q); inputRef.current?.focus(); };
  const onSuggestion = (s: Suggestion) => send(`${s.title || s.path}에 대해 알려줘`);
  const indexed = (regs?.items ?? []).filter((r) => r.status === 'INDEXED');

  return (
    <div className="flex h-[calc(100vh-56px-48px)] min-h-[560px] overflow-hidden rounded-lg border bg-white shadow-sm">
      {/* 대화 목록 */}
      <aside className="flex w-60 shrink-0 flex-col border-r bg-slate-50">
        <div className="p-3"><Button className="w-full" variant="outline" onClick={() => navigate('/chat')}><Plus /> 새 대화</Button></div>
        <div className="scrollbar-thin flex-1 overflow-auto px-2 pb-2">
          {(sessions?.items ?? []).map((s) => (
            <button key={s.session_id} onClick={() => navigate(`/chat/${s.session_id}`)}
              className={cn('mb-0.5 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-white', sid === s.session_id && 'bg-white font-semibold shadow-sm')}>
              <MessageSquare className="h-3.5 w-3.5 shrink-0 text-slate-400" /><span className="truncate">{s.title || '새 대화'}</span>
            </button>
          ))}
          {sessions && sessions.items.length === 0 && <div className="px-2 py-4 text-xs text-muted-foreground">대화가 없습니다</div>}
        </div>
      </aside>

      {/* 본문 */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2.5">
          <div className="font-semibold">규정·매뉴얼 챗봇</div>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            범위:
            <Select value={scope} onValueChange={setScope} disabled={!!sid}>
              <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">전체 규정</SelectItem>
                {indexed.map((r) => <SelectItem key={r.id} value={r.id}>{r.title} v{r.version}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </header>

        <div className="scrollbar-thin flex-1 space-y-4 overflow-auto px-6 py-4">
          {messages.length === 0 && !streaming && (
            <Empty icon={<MessageSquare />} title="규정에 대해 질문해 보세요" description="예: 계약보증금은 얼마야? · 출장비 한도는? · 근거 조·항·목과 함께 답변합니다." />
          )}
          {messages.map((m, i) => (
            <MessageBubble
              key={m.id}
              message={m}
              streaming={streaming && i === messages.length - 1 && m.role === 'assistant' && m.id.startsWith('tmp-a') ? streaming : undefined}
              onCitation={setCitation}
              onFeedback={m.role === 'assistant' && !m.id.startsWith('tmp-') ? (mid, rating) => feedback.mutate({ mid, rating }, { onError: (e) => toast.error(errorMessage(e)) }) : undefined}
              onSuggestion={onSuggestion}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={onSubmit} className="flex items-end gap-2 border-t px-4 py-3">
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }}
            placeholder="규정에 대해 질문하세요… (Enter 전송, Shift+Enter 줄바꿈)"
            className="min-h-[44px] max-h-40 resize-none"
            rows={1}
          />
          {streaming ? (
            <Button type="button" variant="outline" onClick={() => abortRef.current?.abort()}><Square /> 중단</Button>
          ) : (
            <Button type="submit" disabled={!input.trim()}><SendHorizonal /> 전송</Button>
          )}
        </form>
      </section>

      <EvidenceModal citation={citation} onClose={() => setCitation(null)} onAskAgain={askAgain} />
    </div>
  );
}
