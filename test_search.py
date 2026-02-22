import sys
sys.path.insert(0, "/app")

from rag.embeddings import embeddings_generator
from rag.vector_store import vector_store

query1 = "test"
query2 = "რა არის დღგ?"

for query in [query1, query2]:
    print(f"\nQuery: {query}")
    embedding = embeddings_generator.encode_query(query)
    
    # Search without language filter
    results1 = vector_store.search(embedding, n_results=5)
    ids_count1 = len(results1["ids"][0]) if results1.get("ids") else 0
    print(f"  Without filter: {ids_count1} results")
    
    # Search with language filter
    results2 = vector_store.search(embedding, n_results=5, where={"language": "ka"})
    ids_count2 = len(results2["ids"][0]) if results2.get("ids") else 0
    print(f"  With language=ka: {ids_count2} results")
    
    if results2.get("metadatas") and results2["metadatas"][0]:
        print(f"  First result metadata: {results2['metadatas'][0][0]}")
