#!/bin/bash
# RAG Build Management Script
# Usage: ./rag_build.sh [command] [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAG_DIR="$SCRIPT_DIR/backend/app/rag"
VENV="$SCRIPT_DIR/backend/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

echo_success() {
    echo -e "${GREEN}✅${NC} $1"
}

echo_error() {
    echo -e "${RED}❌${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

# Check if venv exists
if [ ! -f "$VENV/bin/python" ]; then
    echo_error "Virtual environment not found at $VENV"
    exit 1
fi

# Activate venv
source "$VENV/bin/activate"

# Commands
case "${1:-help}" in
    build)
        echo_info "Building RAG index from corpus..."
        cd "$SCRIPT_DIR/backend"
        
        CORPUS="${2:-app/rag/gaia_corpus.txt}"
        MODEL="${3:-sentence-transformers/all-MiniLM-L6-v2}"
        
        if [ ! -f "$CORPUS" ]; then
            echo_error "Corpus file not found: $CORPUS"
            exit 1
        fi
        
        echo_info "Corpus: $CORPUS"
        echo_info "Model: $MODEL"
        echo_info "Output: $RAG_DIR"
        
        python -m app.rag.build \
            --corpus "$CORPUS" \
            --model "$MODEL" \
            --output "$RAG_DIR"
        
        if [ $? -eq 0 ]; then
            echo_success "RAG index built successfully"
        else
            echo_error "Failed to build RAG index"
            exit 1
        fi
        ;;
    
    status)
        echo_info "RAG Index Status"
        echo "=================="
        
        if [ -f "$RAG_DIR/metadata.json" ]; then
            echo_success "Metadata file exists"
            echo ""
            echo "Contents:"
            cat "$RAG_DIR/metadata.json" | python -m json.tool
        else
            echo_warning "No metadata.json found"
        fi
        
        if [ -f "$RAG_DIR/gaia_chunks.json" ]; then
            CHUNK_COUNT=$(python -c "import json; f=open('$RAG_DIR/gaia_chunks.json'); data=json.load(f); print(len(data))")
            echo_success "Chunks file exists ($CHUNK_COUNT chunks)"
        else
            echo_warning "No gaia_chunks.json found"
        fi
        
        if [ -f "$RAG_DIR/gaia_corpus.txt" ]; then
            SIZE=$(wc -c < "$RAG_DIR/gaia_corpus.txt")
            echo_success "Corpus file exists ($SIZE bytes)"
        else
            echo_warning "No gaia_corpus.txt found"
        fi
        ;;
    
    test)
        echo_info "Testing RAG pipeline..."
        cd "$SCRIPT_DIR/backend"
        
        python -c "
from app.rag.pipeline import RAGPipeline

try:
    pipeline = RAGPipeline(embedding_backend='dummy', vector_backend='memory')
    print('✅ Pipeline created successfully')
except Exception as e:
    print(f'❌ Error creating pipeline: {e}')
    exit(1)
"
        ;;
    
    clean)
        echo_warning "Removing RAG artifacts..."
        rm -f "$RAG_DIR/gaia_chunks.json"
        rm -f "$RAG_DIR/gaia_embeddings.npy"
        rm -f "$RAG_DIR/metadata.json"
        echo_success "Cleaned up RAG artifacts"
        ;;
    
    help)
        cat << EOF
${BLUE}RAG Build Management${NC}

Usage: $0 [command] [options]

Commands:
  build [corpus] [model]
      Build FAISS index from corpus file
      Args:
        corpus   - Path to corpus file (default: app/rag/gaia_corpus.txt)
        model    - HuggingFace model (default: sentence-transformers/all-MiniLM-L6-v2)
      
      Examples:
        $0 build
        $0 build app/rag/gaia_corpus.txt sentence-transformers/all-mpnet-base-v2
  
  status
      Show RAG index status and metadata
  
  test
      Test RAG pipeline initialization
  
  clean
      Remove RAG artifacts (chunks, embeddings, metadata)
  
  help
      Show this help message

Files:
  gaia_corpus.txt       - Consolidated corpus text
  gaia_chunks.json      - Pre-built chunks with metadata
  gaia_embeddings.npy   - Embedding vectors (numpy)
  metadata.json         - Index metadata and configuration

Examples:
  $0 build
  $0 status
  $0 test
  $0 clean

EOF
        ;;
    
    *)
        echo_error "Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
