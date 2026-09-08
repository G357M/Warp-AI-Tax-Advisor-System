import type { Metadata } from 'next';
import { LegalDocumentPage } from '@/components/legal/LegalDocumentPage';

export const metadata: Metadata = { title: 'Contact — Tax Advisor' };
export default function ContactPage() { return <LegalDocumentPage slug="contact" />; }
