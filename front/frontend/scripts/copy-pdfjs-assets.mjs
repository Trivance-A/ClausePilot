// pdf.js가 CJK(한글 등) CID 폰트를 그리려면 cMap과 표준 폰트 파일이 필요하다.
// node_modules/pdfjs-dist 의 자산을 public/ 으로 복사해 /cmaps/, /standard_fonts/ 경로로 서빙한다 (postinstall).
import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const src = join(root, 'node_modules', 'pdfjs-dist');
const pairs = [
  [join(src, 'cmaps'), join(root, 'public', 'cmaps')],
  [join(src, 'standard_fonts'), join(root, 'public', 'standard_fonts')],
];
for (const [from, to] of pairs) {
  if (!existsSync(from)) { console.warn(`[pdfjs-assets] skip: ${from} not found`); continue; }
  mkdirSync(to, { recursive: true });
  cpSync(from, to, { recursive: true });
  console.log(`[pdfjs-assets] copied ${from} -> ${to}`);
}
