# 계약검증 AI — Frontend

AI 기반 계약서 검증 및 규정 챗봇 시스템의 프론트엔드 (설계산출물 00~06 기준 구현).

- React 18 · Vite · TypeScript · TanStack Query · Zustand · Tailwind · shadcn/ui 스타일 컴포넌트(Radix) · pdf.js
- 백엔드 없이 확인할 수 있도록 **MSW 목 서버**(SSE 스트리밍·목 PDF 포함) 내장

## 실행

```bash
npm install
npm run dev:mock     # 백엔드 없이 목 API로 실행 (http://localhost:3000)
npm run dev          # 실제 백엔드(FastAPI :8000)로 /api 프록시
npm run build        # tsc --noEmit + vite build
```

목 모드 로그인: 이메일이 `admin`으로 시작하면 관리자, 그 외는 사용자 (비밀번호 아무거나).

환경변수(`.env.example` 참고): `VITE_API_BASE`(기본 `/api/v1`), `VITE_USE_MOCK`.

## 화면 ↔ 경로 (04_화면설계서)

| 화면 | 경로 | 파일 |
|---|---|---|
| SC-01 로그인 | `/login` | `pages/LoginPage.tsx` |
| SC-02 계약서 목록 (5초 폴링, 실패 툴팁, 재처리) | `/documents` | `pages/DocumentsPage.tsx` |
| SC-03 업로드 모달 + 진행 카드 | 모달 | `components/documents/UploadModal.tsx`, `ProgressCard.tsx` |
| SC-04 PDF 하이라이팅 Viewer (V-1~V-14) | `/documents/:id/viewer?field=` | `pages/ViewerPage.tsx`, `components/viewer/*` |
| SC-05 위험조항 패널 | Viewer 우측 탭 | `components/viewer/RiskPanel.tsx` |
| SC-06 보증신청 Auto-fill Demo | `/guarantee/new` | `pages/GuaranteePage.tsx`, `components/guarantee/AutofillForm.tsx` |
| SC-07 규정 챗봇 (SSE 멀티턴) | `/chat`, `/chat/:sid` | `pages/ChatPage.tsx`, `components/chat/*` |
| SC-08 근거 팝업 | 모달 | `components/chat/EvidenceModal.tsx` |
| SC-09 규정 문서 관리 (구조보기) | `/admin/regulations` | `pages/AdminRegulationsPage.tsx`, `components/admin/*` |
| SC-10 대시보드 | `/admin/dashboard` | `pages/AdminDashboardPage.tsx` |
| SC-11 평가 결과 | `/admin/eval` | `pages/AdminEvalPage.tsx` |

## 구조

```
src/
  types/api.ts        03_API_명세서 기반 타입 (bbox = [x0,y0,x1,y1] 0~1 정규화)
  lib/api.ts          fetch 클라이언트 (JWT 헤더, 에러 포맷, 401 자동 로그아웃, 503 → AI 서버 다운 배너)
  lib/sse.ts          POST + text/event-stream 파서 (status/token/citation/done)
  lib/pdf.ts, bbox.ts pdf.js 로더(워커 번들), 정규화 좌표 ↔ px 변환
  api/*.ts            도메인별 TanStack Query 훅
  stores/*.ts         auth(persist) · system(AI 다운) · viewer(선택/스크롤/선택모드)
  components/ui/*     shadcn/ui 스타일 (button, dialog, tabs, select, …)
  components/viewer/* PdfViewer(연속 스크롤·줌·검색) · PageView(캔버스+오버레이) · HighlightBox(드래그/리사이즈/우클릭 삭제) · SelectionLayer(드래그 지정)
  mocks/*             MSW 핸들러·픽스처·pdf-lib 목 PDF 생성
```

## 설계서 대비 구현 메모

- 항목 색상은 `GET /extractions` 의 `color_map`만 사용(프론트 하드코딩 없음). 위험 = 빗금 + H/M/L 배지, 수동 = 점선.
- Viewer 키보드: ↑↓ 항목 이동 · Enter 위치 이동 · Esc 선택 모드 해제. 관리자만 오버레이 드래그·리사이즈·삭제.
- `?field=contract_amount` 진입 시 해당 항목으로 자동 스크롤(V-13) — Auto-fill Demo의 🔗 링크가 사용.
- 챗봇: `stream:true` SSE. `[n]` 클릭 → 근거 팝업. NOT_FOUND 시 유사 조항 제안 클릭으로 재질의.
- 명세에 없어 **가정한 엔드포인트**: `GET /regulations/{id}/pdf` (근거 팝업 페이지 렌더용), `GET /eval/runs` (실행 이력, 없으면 빈 목록 처리), citation의 선택 필드 `node_id` (없으면 quoted_span만 표시).
- 목 PDF는 pdf-lib 표준 폰트 제약으로 영문 텍스트이며, 라인 좌표는 `/lines`·하이라이트 bbox와 동일 소스(`mocks/fixtures.ts`)에서 생성됩니다.
