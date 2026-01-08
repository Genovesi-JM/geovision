# backend/app/rag/build.py
import faiss
import json
from sentence_transformers import SentenceTransformer
from rag.splitter import split_text

model = SentenceTransformer("all-MiniLM-L6-v2")

with open("gaia_corpus.txt", "r", encoding="utf8") as f:
    text = f.read()

chunks = split_text(text)
vectors = model.encode(chunks)

index = faiss.IndexFlatL2(vectors.shape[1])
index.add(vectors)

faiss.write_index(index, "gaia.idx")

with open("gaia_chunks.json", "w") as f:
    json.dump(chunks, f)
