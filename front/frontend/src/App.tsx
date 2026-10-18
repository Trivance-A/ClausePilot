import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { RequireAuth } from '@/components/layout/RequireAuth';
import { LoginPage } from '@/pages/LoginPage';
import { DocumentsPage } from '@/pages/DocumentsPage';
import { ViewerPage } from '@/pages/ViewerPage';
import { GuaranteePage } from '@/pages/GuaranteePage';
import { ChatPage } from '@/pages/ChatPage';
import { AdminRegulationsPage } from '@/pages/AdminRegulationsPage';
import { AdminDashboardPage } from '@/pages/AdminDashboardPage';
import { AdminEvalPage } from '@/pages/AdminEvalPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/documents" replace />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:id/viewer" element={<ViewerPage />} />
          <Route path="/guarantee/new" element={<GuaranteePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sid" element={<ChatPage />} />
          <Route element={<RequireAuth admin />}>
            <Route path="/admin" element={<Navigate to="/admin/regulations" replace />} />
            <Route path="/admin/regulations" element={<AdminRegulationsPage />} />
            <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
            <Route path="/admin/eval" element={<AdminEvalPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/documents" replace />} />
    </Routes>
  );
}
