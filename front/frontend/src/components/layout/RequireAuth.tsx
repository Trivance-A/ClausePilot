import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { useMe } from '@/api/auth';

export function RequireAuth({ admin = false }: { admin?: boolean }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  // 토큰이 있으면 /auth/me 로 사용자 정보 동기화 (만료 시 401 → 자동 로그아웃)
  useMe(!!token && !admin);

  if (!token) return <Navigate to="/login" replace state={{ from: location }} />;
  if (admin && user?.role !== 'admin') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 py-24 text-center">
        <div className="text-lg font-semibold">관리자 전용 화면입니다</div>
        <div className="text-sm text-muted-foreground">관리자 계정으로 로그인해 주세요. (403 FORBIDDEN)</div>
      </div>
    );
  }
  return <Outlet />;
}
