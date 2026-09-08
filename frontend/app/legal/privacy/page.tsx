import type { Metadata } from 'next';
import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';

export const metadata: Metadata = { title: 'Privacy policy — Tax Advisor' };
export default function PrivacyPage() { return <LegalDocumentPage slug="privacy" />; }
