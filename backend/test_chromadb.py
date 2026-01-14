"""
Test ChromaDB connection and basic operations.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from rag.vector_store import vector_store
from rag.embeddings import embeddings_generator

def test_chromadb():
    """Test ChromaDB functionality."""
    print("\n🔍 Testing ChromaDB...")
    
    # Check if vector store is initialized
    if vector_store.client is None:
        print("❌ Vector store not initialized")
        return False
    
    print(f"✅ Vector store initialized")
    print(f"📊 Current document count: {vector_store.get_count()}")
    
    # Test adding a document
    print("\n📝 Testing document addition...")
    test_text = "This is a test document about Georgian tax law."
    test_embedding = embeddings_generator.encode([test_text])
    
    if test_embedding and len(test_embedding) > 0:
        print(f"✅ Generated embedding: dimension {len(test_embedding[0])}")
        
        # Add to vector store
        success = vector_store.add_documents(
            ids=["test_doc_1"],
            embeddings=test_embedding,
            documents=[test_text],
            metadatas=[{"type": "test", "source": "manual"}]
        )
        
        if success:
            print("✅ Document added successfully")
            print(f"📊 New document count: {vector_store.get_count()}")
        else:
            print("❌ Failed to add document")
            return False
    else:
        print("❌ Failed to generate embedding")
        return False
    
    # Test search
    print("\n🔎 Testing vector search...")
    query_text = "Georgian tax"
    query_embedding = embeddings_generator.encode_query(query_text)
    
    if query_embedding and len(query_embedding) > 0:
        results = vector_store.search(query_embedding, n_results=1)
        
        if results and results.get("documents") and len(results["documents"][0]) > 0:
            print("✅ Search successful")
            print(f"📄 Found document: {results['documents'][0][0][:50]}...")
            print(f"📏 Distance: {results['distances'][0][0]:.4f}")
        else:
            print("⚠ No results found")
    else:
        print("❌ Failed to generate query embedding")
        return False
    
    print("\n✅ All ChromaDB tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_chromadb()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
