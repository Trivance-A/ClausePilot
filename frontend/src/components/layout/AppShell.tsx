import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown, FileCheck2, LogOut, ShieldCheck, UserRound } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { AiDownBanner } from '@/components/layout/AiDownBanner';

const NAV = [
  { to: '/documents', label: '계약서 검증', match: /^\/documents/ },
  { to: '/guarantee/new', label: '보증신청 Demo', match: /^\/guarantee/ },
  { to: '/chat', label: '규정 챗봇', match: /^\/chat/ },
];
const ADMIN_NAV = [
  { to: '/admin/regulations', label: '규정 문서 관리' },
  { to: '/admin/dashboard', label: '작업·로그 대시보드' },
  { to: '/admin/eval', label: '평가 결과' },
];

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isAdmin = user?.role === 'admin';
  const isViewer = /^\/documents\/[^/]+\/viewer/.test(pathname);

  return (
    <div className="flex h-full min-h-screen flex-col">
      {/* 상단 GNB 56px */}
      <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-6 bg-gnb px-5 text-gnb-foreground shadow">
        <NavLink to="/documents" className="flex items-center gap-2 text-[15px] font-bold tracking-tight">
          <FileCheck2 className="h-5 w-5 text-sky-300" /> 계약검증 AI
        </NavLink>
        <nav className="flex items-center gap-1 text-sm">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={() => cn('rounded-md px-3 py-1.5 transition-colors hover:bg-white/10', n.match.test(pathname) ? 'bg-white/15 font-semibold text-white' : 'text-slate-200')}
            >
              {n.label}
            </NavLink>
          ))}
          {isAdmin && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className={cn('flex items-center gap-1 rounded-md px-3 py-1.5 transition-colors hover:bg-white/10', pathname.startsWith('/admin') ? 'bg-white/15 font-semibold text-white' : 'text-slate-200')}>
                  <ShieldCheck className="h-4 w-4" /> 관리자 <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {ADMIN_NAV.map((a) => (
                  <DropdownMenuItem key={a.to} onSelect={() => navigate(a.to)}>{a.label}</DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {import.meta.env.VITE_USE_MOCK === 'true' && (
            <span className="rounded bg-amber-400/90 px-1.5 py-0.5 text-[11px] font-bold text-slate-900">MOCK</span>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 hover:bg-white/10">
                <UserRound className="h-4 w-4" /> {user?.name ?? '사용자'}
                <span className="rounded bg-white/15 px-1 text-[10px]">{isAdmin ? '관리자' : '사용자'}</span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <div className="px-2 py-1.5 text-xs text-muted-foreground">{user?.email ?? ''}</div>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => { logout(); navigate('/login'); }}><LogOut /> 로그아웃</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <AiDownBanner />
      <main className={cn('flex-1', isViewer ? 'flex min-h-0 flex-col' : 'mx-auto w-full max-w-[1400px] px-6 py-6')}>
        <Outlet />
      </main>
    </div>
  );
}
