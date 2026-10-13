import os
import json
import numpy as np
import ollama

EMBED_MODEL = "nomic-embed-text"
KNOWLEDGE_DIR = "knowledge"
INDEX_FILE = "knowledge_index_ollama.json"   # new name: the old Gemini index can't be mixed in
MIN_SCORE = 0.60       # starting guess. Retune it with test_rag.py (see Step E)
_index = None


def embed(texts, task):
    # This model works best with a short label in front of the text
    prefix = "search_document: " if task == "RETRIEVAL_DOCUMENT" else "search_query: "
    result = ollama.embed(model=EMBED_MODEL, input=[prefix + t for t in texts])
    arr = np.array(result.embeddings, dtype=np.float32)
    arr /= np.linalg.norm(arr, axis=1, keepdims=True)
    return arr


def chunk_text(text, size=150, overlap=25):
    words = text.split()
    chunks = []
    for start in range(0, len(words), size - overlap):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks


def build_index():
    if not os.path.isdir(KNOWLEDGE_DIR):
        os.makedirs(KNOWLEDGE_DIR)
        print("Created the 'knowledge' folder. Add a .txt file with your notes, then run again.")
        return
    chunks = []
    for name in os.listdir(KNOWLEDGE_DIR):
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(KNOWLEDGE_DIR, name), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if len(line.split()) <= 150:
                    chunks.append(line)
                else:
                    chunks += chunk_text(line)
    if not chunks:
        print("No notes found. Add .txt files to the knowledge folder.")
        return
    vectors = embed(chunks, "RETRIEVAL_DOCUMENT")
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"chunks": chunks, "vectors": vectors.tolist()}, f)
    print(f"Done! Stored {len(chunks)} chunks.")


def load_index():
    global _index
    if _index is None and os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _index = {
            "chunks": data["chunks"],
            "vectors": np.array(data["vectors"], dtype=np.float32),
        }
    return _index


def retrieve(question, k=3, min_score=MIN_SCORE):
    index = load_index()
    if not index:
        return []
    q = embed([question], "RETRIEVAL_QUERY")[0]
    scores = index["vectors"] @ q
    best = np.argsort(scores)[::-1][:k]
    return [(index["chunks"][i], float(scores[i]))
            for i in best if scores[i] >= min_score]


if __name__ == "__main__":
    build_index()