"""
Update document titles from their markdown content.
"""
import sys
sys.path.insert(0, "/app")

from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.vector_store import vector_store

def extract_title_from_markdown(markdown_content: str) -> str:
    """Extract title from markdown content."""
    lines = markdown_content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Remove common suffixes
        if ' - infohub.rs.ge' in line:
            title = line.split(' - infohub.rs.ge')[0].strip()
            if title:
                return title
        elif line.startswith('#'):
            # Fallback to first heading
            title = line.lstrip('#').strip()
            if title and title != 'დოკუმენტის სტატისტიკა':
                return title
        elif len(line) > 10 and not line.startswith('[') and not line.startswith('!'):
            # First substantial non-markdown line
            return line[:200]
    
    return 'Untitled'

def main():
    db = SessionLocal()
    
    # Get all documents
    documents = db.query(Document).all()
    print(f"Found {len(documents)} documents")
    
    updated_count = 0
    updated_chunks = 0
    
    for doc in documents:
        old_title = doc.title
        new_title = extract_title_from_markdown(doc.full_text)
        
        if new_title != old_title:
            print(f"\nDocument {doc.id}:")
            print(f"  Old title: {old_title}")
            print(f"  New title: {new_title}")
            
            # Update document title
            doc.title = new_title
            updated_count += 1
            
            # Update chunks in vector store
            chunks = db.query(DocumentChunk).filter_by(document_id=doc.id).all()
            for chunk in chunks:
                vector_id = f"doc_{doc.id}_chunk_{chunk.id}"
                
                # Update metadata in ChromaDB
                try:
                    vector_store.collection.update(
                        ids=[vector_id],
                        metadatas=[{
                            'document_id': str(doc.id),
                            'chunk_id': str(chunk.id),
                            'title': new_title,
                            'source_url': doc.source_url,
                            'document_type': doc.document_type,
                            'language': doc.language,
                            'source': 'infohub.rs.ge',
                            'chunk_index': chunk.chunk_index,
                        }]
                    )
                    updated_chunks += 1
                except Exception as e:
                    print(f"  Error updating chunk {chunk.id}: {e}")
    
    db.commit()
    db.close()
    
    print(f"\n✓ Updated {updated_count} documents")
    print(f"✓ Updated {updated_chunks} chunks in vector store")

if __name__ == "__main__":
    main()
