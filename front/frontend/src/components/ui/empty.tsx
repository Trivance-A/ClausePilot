import type { ReactNode } from 'react';
export function Empty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
      {icon && <div className="text-slate-300 [&_svg]:size-10">{icon}</div>}
      <div className="text-sm font-medium text-foreground">{title}</div>
      {description && <div className="text-xs">{description}</div>}
      {action}
    </div>
  );
}
