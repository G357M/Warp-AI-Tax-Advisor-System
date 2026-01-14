"""
Test complete RAG pipeline functionality.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from rag.pipeline import rag_pipeline

def test_rag_pipeline():
    """Test complete RAG pipeline."""
    print("\n🚀 Testing RAG Pipeline...")
    
    # Get stats
    print("\n📊 Pipeline Statistics:")
    stats = rag_pipeline.get_stats() if hasattr(rag_pipeline, 'get_stats') else {}
    if stats:
        for key, value in stats.items():
            print(f"  • {key}: {value}")
    
    # Add test documents
    print("\n📝 Adding test documents...")
    test_docs = [
        "В Грузии НДС составляет 18% и применяется к большинству товаров и услуг.",
        "Компании должны регистрироваться в качестве плательщиков НДС если годовой оборот превышает 100,000 лари.",
        "Корпоративный налог в Грузии составляет 15% от распределенной прибыли.",
        "Малые предприятия с оборотом менее 500,000 лари могут использовать упрощенную систему налогообложения.",
    ]
    
    test_metadata = [
        {"source": "test", "type": "vat", "language": "ru"},
        {"source": "test", "type": "vat_registration", "language": "ru"},
        {"source": "test", "type": "corporate_tax", "language": "ru"},
        {"source": "test", "type": "simplified_tax", "language": "ru"},
    ]
    
    # Check if pipeline has add_documents method
    if hasattr(rag_pipeline, 'add_documents'):
        # Using new API
        success = rag_pipeline.add_documents(
            texts=test_docs,
            metadatas=test_metadata,
        )
    else:
        # Fallback to vector_store directly
        from rag.embeddings import embeddings_generator
        from rag.vector_store import vector_store
        import uuid
        
        embeddings = embeddings_generator.encode(test_docs)
        ids = [str(uuid.uuid4()) for _ in test_docs]
        success = vector_store.add_documents(
            ids=ids,
            embeddings=embeddings,
            documents=test_docs,
            metadatas=test_metadata,
        )
    
    if success:
        print(f"✅ Added {len(test_docs)} test documents")
    else:
        print("❌ Failed to add documents")
        return False
    
    # Test query
    print("\n🔍 Testing query processing...")
    test_query = "Какой размер НДС в Грузии?"
    
    result = rag_pipeline.process_query(test_query, language="ru")
    
    if result:
        print(f"\n📄 Query: {test_query}")
        print(f"\n💬 Answer: {result.get('response', 'No response')[:200]}...")
        print(f"\n📚 Retrieved {result.get('retrieved_count', 0)} documents")
        
        sources = result.get('sources', [])
        if sources:
            print(f"📖 Sources ({len(sources)}):")
            for i, source in enumerate(sources[:3], 1):
                print(f"  {i}. {source.get('title', 'Unknown')} (relevance: {source.get('relevance', 0):.2f})")
        
        print("\n✅ RAG Pipeline test passed!")
        return True
    else:
        print("❌ Query processing failed")
        return False

if __name__ == "__main__":
    try:
        success = test_rag_pipeline()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
