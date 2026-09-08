import type { Metadata } from 'next';
import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';

export const metadata: Metadata = { title: 'Refunds and cancellation — Tax Advisor' };
export default function RefundsPage() { return <LegalDocumentPage slug="refunds" />; }
