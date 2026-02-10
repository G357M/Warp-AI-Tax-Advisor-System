"""
Simple test server to verify FastAPI setup.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="InfoHub Test Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "running",
        "message": "InfoHub AI Tax Advisor Test Server"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/v1/public/health")
def public_health():
    return {
        "status": "healthy",
        "database": "not connected (test mode)",
        "redis": "not connected (test mode)",
        "chromadb": "not connected (test mode)"
    }

@app.post("/api/v1/public/query")
def public_query(query: dict):
    return {
        "response": "This is a test response. The full system with AI is loading. Please install all dependencies to use the real RAG system.",
        "sources": [],
        "retrieved_count": 0,
        "processing_time": 0.1
    }

if __name__ == "__main__":
    import os
    
    port = int(os.getenv("API_PORT", "8000"))
    
    print("=" * 60)
    print("🚀 InfoHub AI Test Server Starting...")
    print("=" * 60)
    print(f"\n📍 Server will run on: http://localhost:{port}")
    print(f"📖 API Docs: http://localhost:{port}/docs")
    print("\n💡 This is a simplified test server.")
    print("   Full system requires all dependencies installed.\n")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
