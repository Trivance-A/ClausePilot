import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { MOCK_LINES, PAGE_H, PAGE_W } from './fixtures';

let contractPdf: Promise<Uint8Array> | null = null;
let regulationPdf: Promise<Uint8Array> | null = null;

/** 계약서 목 PDF: MOCK_LINES 의 bbox 위치에 텍스트를 그려 /lines·하이라이트와 좌표가 일치하도록 생성 */
export function getContractPdf() {
  contractPdf ??= (async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const bold = await doc.embedFont(StandardFonts.HelveticaBold);
    const pageCount = Math.max(...MOCK_LINES.map((l) => l.page));
    for (let p = 1; p <= pageCount; p++) {
      const page = doc.addPage([PAGE_W, PAGE_H]);
      page.drawRectangle({ x: 36, y: 36, width: PAGE_W - 72, height: PAGE_H - 72, borderColor: rgb(0.85, 0.85, 0.85), borderWidth: 0.5 });
      page.drawText(`- ${p} -`, { x: PAGE_W / 2 - 10, y: 20, size: 9, font, color: rgb(0.5, 0.5, 0.5) });
      for (const l of MOCK_LINES.filter((x) => x.page === p)) {
        const [x0, y0, , y1] = l.bbox;
        const h = (y1 - y0) * PAGE_H;
        const size = l.size ?? Math.min(11, h * 0.62);
        page.drawText(l.text, { x: x0 * PAGE_W + 2, y: PAGE_H - y1 * PAGE_H + (h - size) / 2 + 1, size, font: l.size ? bold : font, color: rgb(0.1, 0.1, 0.1) });
      }
      if (p === 2) {
        // 스캔 페이지 느낌: 약간의 노이즈 라인
        for (let i = 0; i < 6; i++) page.drawLine({ start: { x: 60 + i * 80, y: 700 }, end: { x: 90 + i * 80, y: 700 }, thickness: 0.3, color: rgb(0.8, 0.8, 0.8) });
      }
    }
    return doc.save();
  })();
  return contractPdf;
}

/** 규정 목 PDF (10페이지) — 근거 팝업의 페이지·bbox 하이라이트 시연용 */
export function getRegulationPdf() {
  regulationPdf ??= (async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const bold = await doc.embedFont(StandardFonts.HelveticaBold);
    const texts: Record<number, { y: number; t: string; b?: boolean }[]> = {
      1: [{ y: 0.10, t: 'CONTRACT AFFAIRS REGULATION (v2, effective 2025-01-01)', b: true }, { y: 0.17, t: 'CHAPTER 1  GENERAL PROVISIONS', b: true }, { y: 0.22, t: 'Article 1 (Purpose) This regulation sets forth basic matters on contract affairs.' }, { y: 0.32, t: 'Article 2 (Definitions) Terms used in this regulation are defined as follows.' }],
      4: [{ y: 0.12, t: 'CHAPTER 3  CONCLUSION OF CONTRACTS', b: true }, { y: 0.20, t: 'Article 11 (Bid Bond)', b: true }, { y: 0.24, t: '(1) A bidder shall deposit a bid bond of 5/100 or more of the bid amount.' }, { y: 0.36, t: 'Article 12 (Contract Guarantee)', b: true }, { y: 0.39, t: '(1) The contract officer shall require the counterparty to deposit a contract guarantee.' }, { y: 0.44, t: '(2) The contract guarantee shall be 10/100 or more of the contract amount.' }, { y: 0.49, t: '(3) Notwithstanding paragraph (2), the guarantee may be reduced where necessary.' }],
      5: [{ y: 0.15, t: 'Article 13 (Exemption of Guarantee)', b: true }, { y: 0.19, t: '(1) The guarantee may be exempted for contracts with public institutions.' }, { y: 0.40, t: 'Article 15 (Defect Repair Guarantee) 2/100 to 10/100 of the contract amount.' }],
      9: [{ y: 0.12, t: 'CHAPTER 5  WELFARE', b: true }, { y: 0.20, t: 'Article 7 (Travel Expenses)', b: true }, { y: 0.24, t: '(1) Domestic per diem: KRW 30,000 per day; lodging: actual cost up to KRW 100,000.' }, { y: 0.40, t: 'Article 9 (Meal Expenses) Meals are provided in the cafeteria at the expense of the association.' }],
    };
    for (let p = 1; p <= 10; p++) {
      const page = doc.addPage([PAGE_W, PAGE_H]);
      page.drawText(`Contract Affairs Regulation  -  ${p}`, { x: 60, y: 20, size: 8, font, color: rgb(0.5, 0.5, 0.5) });
      for (const t of texts[p] ?? []) page.drawText(t.t, { x: 0.1 * PAGE_W + 2, y: PAGE_H - t.y * PAGE_H - 12, size: t.b ? 12 : 10.5, font: t.b ? bold : font });
    }
    return doc.save();
  })();
  return regulationPdf;
}
