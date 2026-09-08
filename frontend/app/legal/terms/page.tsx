import type { Metadata } from 'next';
import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';

export const metadata: Metadata = { title: 'Terms of use — Tax Advisor' };
export default function TermsPage() { return <LegalDocumentPage slug="terms" />; }
