'use client';

import { usePathname } from 'next/navigation';

export function SiteFooter() {
  const pathname = usePathname();
  if (pathname?.startsWith('/admin')) return null;

  return (
    <footer className="border-t">
      <div className="mx-auto max-w-page px-6 py-10">
        <div className="flex flex-col justify-between gap-6 sm:flex-row">
          <div>
            <div className="text-sm font-semibold">Tax Advisor</div>
            <p className="mt-1 max-w-md text-[13px] leading-relaxed text-muted-foreground">
              Ответы строятся только на официальной базе: Налоговый кодекс Грузии,
              подзаконные акты, решения советов по рассмотрению споров. Сервис носит
              информационный характер и не заменяет юридическую консультацию.
            </p>
          </div>
          <div className="text-[13px] text-muted-foreground">
            <div>Источник данных: infohub.rs.ge</div>
            <div className="mt-1">© {new Date().getFullYear()} Tax Advisor</div>
          </div>
        </div>
      </div>
    </footer>
  );
}
