import os
import sys
import json
import asyncio

sys.path.insert(0, '/app')

from scraper.firecrawl_scraper import FirecrawlScraper
from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store


async def main():
    if len(sys.argv) != 5:
        raise SystemExit('usage: python - <species> <page> <offset> <doc_batch>')

    species = sys.argv[1]
    page = int(sys.argv[2])
    offset = int(sys.argv[3])
    doc_batch = int(sys.argv[4])

    api_key = os.getenv('FIRECRAWL_API_KEY', 'fc-77900ef0e837476985d88650596d0ec7')
    scraper = FirecrawlScraper(api_key=api_key)
    db = SessionLocal()
    created_or_seen = 0
    new_count = 0
    existing_count = 0
    embedded_new_chunks = 0
    new_doc_ids = []

    try:
        url = f'https://infohub.rs.ge/ka?species={species}&page={page}&pageSize=40'
        result = scraper.scrape_url(url, formats=['markdown', 'links'])
        if not result or 'data' not in result:
            raise RuntimeError(f'failed to scrape listing page: {url}')

        links = result['data'].get('links', []) or []
        dedup = []
        seen = set()
        for link in links:
            if 'infohub.rs.ge' in link and 'document' in link.lower() and link not in seen:
                seen.add(link)
                dedup.append(link)

        selected = dedup[offset:offset + doc_batch]

        for doc_url in selected:
            existed_before = db.query(Document).filter_by(source_url=doc_url).first() is not None
            doc_result = scraper.scrape_url(doc_url)
            if doc_result and 'data' in doc_result:
                doc_data = doc_result['data']
                doc_markdown = doc_data.get('markdown', '')
                doc_metadata = doc_data.get('metadata', {}) or {}
                doc_metadata['species'] = species
                doc_metadata['page'] = page
                doc_metadata['gradual_ingest'] = True
                document = await scraper.process_document(doc_url, doc_markdown, doc_metadata, db)
                if document:
                    created_or_seen += 1
                    if existed_before:
                        existing_count += 1
                    else:
                        new_count += 1
                        new_doc_ids.append(document.id)
            await asyncio.sleep(1.5)

        if new_doc_ids:
            pending_chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id.in_(new_doc_ids))
                .filter(DocumentChunk.embedding.is_(None))
                .order_by(DocumentChunk.created_at)
                .all()
            )
            for start in range(0, len(pending_chunks), 16):
                batch = pending_chunks[start:start + 16]
                texts = [row.content for row in batch]
                ids = [f"doc_{row.document_id}_chunk_{row.id}" for row in batch]
                metas = [
                    {
                        'document_id': str(row.document_id),
                        'chunk_id': str(row.id),
                        'chunk_index': row.chunk_index,
                    }
                    for row in batch
                ]
                embeddings = embeddings_generator.encode(texts)
                vector_store.add_documents(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metas,
                )
                embedded_new_chunks += len(batch)

        print('RESULT_JSON=' + json.dumps({
            'species': species,
            'page': page,
            'offset': offset,
            'doc_batch': doc_batch,
            'total_links': len(dedup),
            'attempted': len(selected),
            'created_or_seen': created_or_seen,
            'new_count': new_count,
            'existing_count': existing_count,
            'embedded_new_chunks': embedded_new_chunks,
        }, ensure_ascii=False))
    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(main())
