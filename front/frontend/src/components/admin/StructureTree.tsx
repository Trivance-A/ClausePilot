import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText } from 'lucide-react';
import { useRegNode, useRegulation } from '@/api/regulations';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import type { RegNode } from '@/types/api';

const LEVEL_LABEL: Record<string, string> = { chapter: '장', section: '절', article: '조', paragraph: '항', item: '호', subitem: '목', appendix: '부칙/별표' };
const NUMBER_FMT = (n: RegNode) => {
  switch (n.level) {
    case 'chapter': return `제${n.number}장`;
    case 'section': return `제${n.number}절`;
    case 'article': return `제${n.number}조`;
    case 'paragraph': return n.number;
    case 'item': return `${n.number}.`;
    case 'subitem': return `${n.number}.`;
    default: return n.number;
  }
};

function TreeNode({ node, depth, selected, onSelect }: { node: RegNode; depth: number; selected: string | null; onSelect: (n: RegNode) => void }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children?.length > 0;
  return (
    <div>
      <div className={cn('flex cursor-pointer items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-slate-100', selected === node.node_id && 'bg-blue-50 font-semibold')} style={{ paddingLeft: depth * 16 + 4 }} onClick={() => onSelect(node)}>
        <button className="h-4 w-4 shrink-0 text-slate-400" onClick={(e) => { e.stopPropagation(); setOpen(!open); }}>
          {hasChildren ? (open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />) : <span className="inline-block h-4 w-4" />}
        </button>
        <span className="text-slate-500">{NUMBER_FMT(node)}</span>
        <span className="truncate">{node.title ? `(${node.title})` : ''}</span>
        {node.page_no && <span className="ml-auto text-[10px] text-slate-400">p{node.page_no}</span>}
      </div>
      {open && hasChildren && node.children.map((c) => <TreeNode key={c.node_id} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />)}
    </div>
  );
}

/** SC-09 [구조보기]: 장·조·항 트리 + 노드 원문 대조 (파싱 검수용) */
export function StructureTreeDialog({ regId, onClose }: { regId: string | null; onClose: () => void }) {
  const { data, isLoading } = useRegulation(regId ?? undefined);
  const [sel, setSel] = useState<RegNode | null>(null);
  const { data: node } = useRegNode(regId, sel?.node_id);
  const count = (nodes: RegNode[]): number => nodes.reduce((a, n) => a + 1 + count(n.children ?? []), 0);

  return (
    <Dialog open={!!regId} onOpenChange={(o) => { if (!o) { onClose(); setSel(null); } }}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileText className="h-4 w-4" /> {data?.title ?? '규정 구조'} {data && <Badge variant="muted">v{data.version}</Badge>}</DialogTitle>
          <DialogDescription>파싱된 장·절·조·항·호·목 트리 {data ? `(노드 ${count(data.tree)}개)` : ''} — 원문과 대조하여 파싱 오류를 검수합니다.</DialogDescription>
        </DialogHeader>
        <div className="grid h-[60vh] grid-cols-[1fr_1fr] gap-4">
          <div className="scrollbar-thin overflow-auto rounded-md border p-2">
            {isLoading && <div className="p-3 text-sm text-muted-foreground">불러오는 중…</div>}
            {data?.tree.map((n) => <TreeNode key={n.node_id} node={n} depth={0} selected={sel?.node_id ?? null} onSelect={setSel} />)}
            {data && data.tree.length === 0 && <div className="p-3 text-sm text-muted-foreground">파싱된 구조가 없습니다.</div>}
          </div>
          <div className="scrollbar-thin overflow-auto rounded-md border bg-slate-50 p-3 text-sm">
            {!sel && <div className="text-muted-foreground">좌측 트리에서 노드를 선택하면 원문이 표시됩니다.</div>}
            {sel && (
              <>
                <div className="mb-1 text-xs text-muted-foreground">{node?.path ?? sel.path} · {LEVEL_LABEL[sel.level] ?? sel.level}{node?.page_no ? ` · p${node.page_no}` : ''}</div>
                <div className="mb-2 font-semibold">{NUMBER_FMT(sel)} {sel.title ? `(${sel.title})` : ''}</div>
                <p className="whitespace-pre-wrap leading-6">{node?.content ?? '(원문 불러오는 중…)'}</p>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
