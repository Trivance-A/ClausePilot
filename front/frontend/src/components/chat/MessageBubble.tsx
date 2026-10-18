import { Fragment, useState } from 'react';
import { Bot, Copy, Loader2, ThumbsDown, ThumbsUp, User } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { ChatMessage, Citation, Suggestion } from '@/types/api';

export interface StreamingState { content: string; citations: Citation[]; stage: string | null; done: boolean }

interface Props {
  message: ChatMessage;
  streaming?: StreamingState;
  onCitation: (c: Citation) => void;
  onFeedback?: (mid: string, rating: 1 | -1) => void;
  onSuggestion?: (s: Suggestion) => void;
}

const STAGES: { key: string; label: string }[] = [{ key: 'rewrite', label: '질의 재작성' }, { key: 'retrieve', label: '검색 중' }, { key: 'generate', label: '답변 생성' }];

/** 본문 내 [n] 인용 태그를 클릭 가능한 칩으로 렌더 */
function renderWithCitations(text: string, citations: Citation[], onCitation: (c: Citation) => void) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((p, i) => {
    const m = p.match(/^\[(\d+)\]$/);
    if (!m) return <Fragment key={i}>{p}</Fragment>;
    const ref = Number(m[1]);
    const c = citations.find((x) => x.ref === ref);
    return (
      <button key={i} type="button" disabled={!c} title={c?.path} onClick={() => c && onCitation(c)}
        className={cn('mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded px-1 align-baseline text-[11px] font-bold', c ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-slate-100 text-slate-400')}>
        {ref}
      </button>
    );
  });
}

export function MessageBubble({ message, streaming, onCitation, onFeedback, onSuggestion }: Props) {
  const [fb, setFb] = useState<1 | -1 | null>(message.feedback ?? null);
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[70%] items-start gap-2">
          <div className="rounded-2xl rounded-tr-sm bg-blue-600 px-4 py-2 text-sm text-white">{message.content}</div>
          <span className="mt-1 rounded-full bg-slate-200 p-1"><User className="h-4 w-4 text-slate-600" /></span>
        </div>
      </div>
    );
  }

  const content = streaming ? streaming.content : message.content;
  const citations = streaming ? streaming.citations : message.citations ?? [];
  const isNotFound = !streaming && message.answer_status === 'NOT_FOUND';
  const isStreaming = !!streaming && !streaming.done;
  const stageIdx = streaming?.stage ? STAGES.findIndex((s) => s.key === streaming.stage) : -1;

  return (
    <div className="flex justify-start">
      <div className="flex w-full max-w-[85%] items-start gap-2">
        <span className="mt-1 rounded-full bg-emerald-100 p-1"><Bot className="h-4 w-4 text-emerald-700" /></span>
        <div className={cn('flex-1 rounded-2xl rounded-tl-sm border px-4 py-3 text-sm', isNotFound ? 'border-amber-200 bg-amber-50' : 'border-emerald-100 bg-emerald-50/60')}>
          {isStreaming && !content && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> 단계:
              {STAGES.map((s, i) => (
                <span key={s.key} className={cn('flex items-center gap-1', i === stageIdx ? 'font-semibold text-emerald-700' : i < stageIdx ? 'text-emerald-600' : 'text-slate-400')}>
                  {i > 0 && <span className="text-slate-300">→</span>}{s.label}{i < stageIdx ? ' ✓' : ''}
                </span>
              ))}
            </div>
          )}
          {content && (
            <p className="whitespace-pre-wrap leading-6">
              {renderWithCitations(content, citations, onCitation)}
              {isStreaming && <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-emerald-700 align-middle" />}
            </p>
          )}
          {isNotFound && message.suggestions && message.suggestions.length > 0 && (
            <div className="mt-2 text-xs">
              <div className="mb-1 text-amber-800">혹시 이런 조항을 찾으시나요?</div>
              <ul className="space-y-0.5">
                {message.suggestions.map((s, i) => (
                  <li key={i}>· <button className="text-blue-700 hover:underline" onClick={() => onSuggestion?.(s)}>{s.title || s.path}</button><span className="ml-1 text-slate-400">{s.path}</span></li>
                ))}
              </ul>
            </div>
          )}
          {citations.length > 0 && (
            <div className="mt-2 rounded-md border border-emerald-200 bg-white p-2 text-xs">
              <div className="mb-1 font-semibold text-emerald-800">근거</div>
              <ul className="space-y-0.5">
                {[...citations].sort((a, b) => a.ref - b.ref).map((c) => (
                  <li key={c.ref}>
                    <button className="text-left text-emerald-700 hover:underline" onClick={() => onCitation(c)}>
                      [{c.ref}] {c.regulation_title} › {c.path.split('>').map((s) => s.trim()).join(' › ')}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!isStreaming && (
            <div className="mt-2 flex items-center gap-1 text-slate-500">
              {onFeedback && (
                <>
                  <Button variant="ghost" size="icon-sm" className={cn(fb === 1 && 'text-emerald-600')} onClick={() => { setFb(1); onFeedback(message.id, 1); }} aria-label="좋아요"><ThumbsUp /></Button>
                  <Button variant="ghost" size="icon-sm" className={cn(fb === -1 && 'text-red-600')} onClick={() => { setFb(-1); onFeedback(message.id, -1); }} aria-label="싫어요"><ThumbsDown /></Button>
                </>
              )}
              <Button variant="ghost" size="icon-sm" onClick={() => navigator.clipboard.writeText(content).then(() => toast.success('복사했습니다'))} aria-label="복사"><Copy /></Button>
              {message.latency_ms !== undefined && <span className="ml-auto text-[11px]">{(message.latency_ms / 1000).toFixed(1)}s</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
