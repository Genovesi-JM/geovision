#!/usr/bin/env python3
"""
RAG Management CLI - Build, test, and manage RAG indices
Usage: python rag_manage.py [command] [options]
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional


class Colors:
    """ANSI color codes"""
    RESET = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'


def log_info(msg: str):
    print(f"{Colors.BLUE}ℹ{Colors.RESET}  {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}✅{Colors.RESET} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}❌{Colors.RESET} {msg}")


def log_warning(msg: str):
    print(f"{Colors.YELLOW}⚠{Colors.RESET}  {msg}")


class RAGManager:
    """Manage RAG build and operations"""
    
    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = Path(__file__).parent
        
        self.project_root = project_root
        self.backend_dir = project_root / "backend"
        self.rag_dir = self.backend_dir / "app" / "rag"
        self.venv_python = self.backend_dir / ".venv" / "bin" / "python"
        
        # Verify paths exist
        if not self.backend_dir.exists():
            raise FileNotFoundError(f"Backend directory not found: {self.backend_dir}")
        
        if not self.venv_python.exists():
            log_warning(f"Virtual environment not found at {self.venv_python}")
            self.venv_python = None
    
    def build_index(
        self,
        corpus: Optional[Path] = None,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> bool:
        """Build RAG index from corpus"""
        if corpus is None:
            corpus = self.rag_dir / "gaia_corpus.txt"
        
        corpus = Path(corpus)
        
        if not corpus.exists():
            log_error(f"Corpus file not found: {corpus}")
            return False
        
        log_info(f"Building RAG index...")
        log_info(f"  Corpus: {corpus}")
        log_info(f"  Model: {model}")
        log_info(f"  Chunk size: {chunk_size}")
        log_info(f"  Chunk overlap: {chunk_overlap}")
        log_info(f"  Output: {self.rag_dir}")
        
        cmd = [
            str(self.venv_python or "python"),
            "-m", "app.rag.build",
            "--corpus", str(corpus),
            "--model", model,
            "--chunk-size", str(chunk_size),
            "--chunk-overlap", str(chunk_overlap),
            "--output", str(self.rag_dir),
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.backend_dir),
                capture_output=False,
            )
            
            if result.returncode == 0:
                log_success("RAG index built successfully")
                return True
            else:
                log_error("Failed to build RAG index")
                return False
        
        except Exception as e:
            log_error(f"Error building RAG index: {e}")
            return False
    
    def show_status(self) -> None:
        """Show RAG index status"""
        log_info("RAG Index Status")
        print("=" * 50)
        print()
        
        # Check metadata
        metadata_file = self.rag_dir / "metadata.json"
        if metadata_file.exists():
            log_success("Metadata file exists")
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)
                
                print("\nMetadata:")
                print(json.dumps(metadata, indent=2))
                print()
            except Exception as e:
                log_error(f"Error reading metadata: {e}")
        else:
            log_warning("No metadata.json found")
            print()
        
        # Check chunks
        chunks_file = self.rag_dir / "gaia_chunks.json"
        if chunks_file.exists():
            try:
                with open(chunks_file) as f:
                    chunks = json.load(f)
                
                if isinstance(chunks, list):
                    log_success(f"Chunks file exists ({len(chunks)} chunks)")
                else:
                    log_warning(f"Chunks file format unexpected")
                print()
            except Exception as e:
                log_error(f"Error reading chunks: {e}")
        else:
            log_warning("No gaia_chunks.json found")
            print()
        
        # Check corpus
        corpus_file = self.rag_dir / "gaia_corpus.txt"
        if corpus_file.exists():
            size = corpus_file.stat().st_size
            size_mb = size / (1024 * 1024)
            log_success(f"Corpus file exists ({size_mb:.2f} MB)")
            print()
        else:
            log_warning("No gaia_corpus.txt found")
            print()
        
        # Check embeddings
        embeddings_file = self.rag_dir / "gaia_embeddings.npy"
        if embeddings_file.exists():
            size = embeddings_file.stat().st_size
            size_mb = size / (1024 * 1024)
            log_success(f"Embeddings file exists ({size_mb:.2f} MB)")
        else:
            log_info("No embeddings file (will be created on build)")
    
    def test_pipeline(self) -> bool:
        """Test RAG pipeline initialization"""
        log_info("Testing RAG pipeline...")
        
        cmd = [
            str(self.venv_python or "python"),
            "-c",
            """
from app.rag.pipeline import RAGPipeline

try:
    log_info('Creating pipeline with dummy embedder...')
    pipeline = RAGPipeline(embedding_backend='dummy', vector_backend='memory')
    log_success('Pipeline created successfully')
    log_success(f'Pipeline initialized with {len(pipeline.vector_store.documents)} documents')
except Exception as e:
    log_error(f'Error creating pipeline: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
""",
        ]
        
        # Inject logging functions
        test_code = """
import sys
sys.path.insert(0, '/Users/genovesimaria/Desktop/geovision')

class Colors:
    RESET = '\\033[0m'
    GREEN = '\\033[0;32m'
    RED = '\\033[0;31m'
    BLUE = '\\033[0;34m'

def log_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.RESET}  {msg}")

def log_success(msg):
    print(f"{Colors.GREEN}✅{Colors.RESET} {msg}")

def log_error(msg):
    print(f"{Colors.RED}❌{Colors.RESET} {msg}")

""" + cmd[2]
        
        cmd[2] = test_code
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.backend_dir),
            )
            return result.returncode == 0
        
        except Exception as e:
            log_error(f"Error testing pipeline: {e}")
            return False
    
    def clean(self, confirm: bool = True) -> bool:
        """Remove RAG artifacts"""
        files_to_remove = [
            self.rag_dir / "gaia_chunks.json",
            self.rag_dir / "gaia_embeddings.npy",
            self.rag_dir / "metadata.json",
        ]
        
        if confirm:
            print("\nFiles to be removed:")
            for f in files_to_remove:
                if f.exists():
                    print(f"  - {f}")
            
            response = input("\nContinue? (y/n): ").strip().lower()
            if response != 'y':
                log_info("Cancelled")
                return False
        
        for f in files_to_remove:
            if f.exists():
                try:
                    f.unlink()
                    log_success(f"Removed {f.name}")
                except Exception as e:
                    log_error(f"Failed to remove {f.name}: {e}")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="RAG Management CLI - Build and manage RAG indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rag_manage.py build
  python rag_manage.py build --corpus app/rag/gaia_corpus.txt --model sentence-transformers/all-mpnet-base-v2
  python rag_manage.py status
  python rag_manage.py test
  python rag_manage.py clean
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build RAG index from corpus")
    build_parser.add_argument(
        "--corpus",
        type=Path,
        help="Corpus file path (default: backend/app/rag/gaia_corpus.txt)",
    )
    build_parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="HuggingFace embedding model (default: sentence-transformers/all-MiniLM-L6-v2)",
    )
    build_parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Chunk size in characters (default: 512)",
    )
    build_parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Chunk overlap in characters (default: 50)",
    )
    
    # Status command
    subparsers.add_parser("status", help="Show RAG index status")
    
    # Test command
    subparsers.add_parser("test", help="Test RAG pipeline initialization")
    
    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Remove RAG artifacts")
    clean_parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompt",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        manager = RAGManager()
    except FileNotFoundError as e:
        log_error(str(e))
        return 1
    
    if args.command == "build":
        success = manager.build_index(
            corpus=args.corpus,
            model=args.model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
        return 0 if success else 1
    
    elif args.command == "status":
        manager.show_status()
        return 0
    
    elif args.command == "test":
        success = manager.test_pipeline()
        return 0 if success else 1
    
    elif args.command == "clean":
        success = manager.clean(confirm=not args.no_confirm)
        return 0 if success else 1
    
    else:
        log_error(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
