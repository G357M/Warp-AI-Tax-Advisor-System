import type { Metadata } from 'next';
import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';

export const metadata: Metadata = { title: 'Access activation — Tax Advisor' };
export default function DeliveryPage() { return <LegalDocumentPage slug="delivery" />; }
