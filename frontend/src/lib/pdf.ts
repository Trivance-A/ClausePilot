import * as pdfjs from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
// Vite가 워커를 정적 자산으로 번들 → Safari 포함 모든 브라우저에서 동일 경로 사용 (OffscreenCanvas 미사용)
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { rawRequest } from '@/lib/api';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const cache = new Map<string, Promise<PDFDocumentProxy>>();

/** 인증 헤더를 붙여 PDF를 내려받은 뒤 pdf.js 문서로 로드 (경로 기준 캐시) */
export function loadPdf(path: string): Promise<PDFDocumentProxy> {
  let p = cache.get(path);
  if (!p) {
    p = rawRequest(path)
      .then((r) => r.arrayBuffer())
      .then((data) => pdfjs.getDocument({ data, cMapUrl: undefined }).promise);
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return p;
}

export function evictPdf(path: string) { cache.delete(path); }
export type { PDFDocumentProxy };
