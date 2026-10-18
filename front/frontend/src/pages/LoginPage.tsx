import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { FileCheck2 } from 'lucide-react';
import { useLogin } from '@/api/auth';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { errorMessage } from '@/lib/api';

export function LoginPage() {
  const token = useAuthStore((s) => s.token);
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/documents';

  if (token) return <Navigate to={from} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email, password }, { onSuccess: () => navigate(from, { replace: true }) });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-blue-50 p-6">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2 text-lg font-bold">
          <FileCheck2 className="h-6 w-6 text-primary" /> 계약검증 AI
        </div>
        <p className="mb-6 text-sm text-muted-foreground">AI 기반 계약서 검증 및 규정 챗봇 시스템</p>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">이메일</Label>
            <Input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@example.com" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">비밀번호</Label>
            <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {login.isError && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{errorMessage(login.error)}</div>}
          <Button type="submit" className="w-full" loading={login.isPending}>로그인</Button>
        </div>
        {import.meta.env.VITE_USE_MOCK === 'true' && (
          <p className="mt-4 text-center text-xs text-muted-foreground">목 모드: admin@… 으로 로그인하면 관리자, 그 외는 사용자</p>
        )}
      </form>
    </div>
  );
}
