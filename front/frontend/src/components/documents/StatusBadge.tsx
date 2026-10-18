import { CheckCircle2, CircleDashed, Loader2, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { DocumentStatus, RegulationStatus } from '@/types/api';

export const STEP_LABEL: Record<string, string> = {
  UPLOADED: '대기', NORMALIZING: '정규화', OCR: 'OCR', EXTRACTING: '추출', RISK: '위험탐지', DONE: '완료', FAILED: '실패',
  normalize: '정규화', ocr: 'OCR', extract: '추출', risk: '위험탐지', parse: '파싱', chunk: '청킹', embed: '임베딩',
};

export function DocStatusBadge({ status, progress, step }: { status: DocumentStatus; progress?: number | null; step?: string | null }) {
  if (status === 'DONE') return <Badge variant="success"><CheckCircle2 className="h-3 w-3" /> 완료</Badge>;
  if (status === 'FAILED') return <Badge variant="danger"><XCircle className="h-3 w-3" /> 실패</Badge>;
  if (status === 'UPLOADED') return <Badge variant="muted"><CircleDashed className="h-3 w-3" /> 대기</Badge>;
  const label = STEP_LABEL[step ?? status] ?? status;
  return (
    <Badge variant="warning"><Loader2 className="h-3 w-3 animate-spin" /> {label}{typeof progress === 'number' ? ` ${progress}%` : ''}</Badge>
  );
}

export function RegStatusBadge({ status }: { status: RegulationStatus }) {
  switch (status) {
    case 'INDEXED': return <Badge variant="success"><CheckCircle2 className="h-3 w-3" /> 색인완료</Badge>;
    case 'FAILED': return <Badge variant="danger"><XCircle className="h-3 w-3" /> 실패</Badge>;
    case 'ARCHIVED': return <Badge variant="muted">보관</Badge>;
    case 'UPLOADED': return <Badge variant="muted"><CircleDashed className="h-3 w-3" /> 대기</Badge>;
    default: return <Badge variant="warning"><Loader2 className="h-3 w-3 animate-spin" /> 파싱중</Badge>;
  }
}
