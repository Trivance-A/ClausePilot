import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import App from '@/App';
import '@/index.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 10_000 } },
});

async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const { startMockWorker } = await import('@/mocks/browser');
    await startMockWorker();
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
          <Toaster richColors position="top-center" closeButton />
        </TooltipProvider>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
bootstrap();
