"""海龟交易法则 PDF 知识库接入脚本。

一次性运行，将 PDF 解析为文本块，向量化后存入 ChromaDB，供 RAG 检索使用。

流程：
    1. PyMuPDF 提取每页文本
    2. LangChain RecursiveCharacterTextSplitter 切片
    3. sentence-transformers 本地嵌入
    4. ChromaDB 持久化存储

用法：
    source .stock/bin/activate.fish
    python backend/knowledge/ingest.py
"""

import sys
from pathlib import Path

# 确保 backend 在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings

from config import PDF_PATH, CHROMA_DB_DIR, CHUNK_SIZE, CHUNK_OVERLAP


def extract_text(pdf_path: Path) -> list[dict]:
    """从 PDF 逐页提取文本，返回 [{page, text}, ...] 列表。"""
    doc = fitz.open(str(pdf_path))
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append({"page": i + 1, "text": text.strip()})
    doc.close()
    return pages


def build_vectorstore() -> None:
    """主流程：提取 → 切片 → 嵌入 → 存入 ChromaDB。"""
    print(f"正在读取 PDF: {PDF_PATH}")
    pages = extract_text(PDF_PATH)
    print(f"共提取 {len(pages)} 页文本")

    print("正在切片...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", " ", ""],
    )

    all_chunks = []
    all_metadata = []
    for p in pages:
        chunks = splitter.split_text(p["text"])
        for chunk in chunks:
            if len(chunk.strip()) < 20:  # 跳过过短的片段
                continue
            all_chunks.append(chunk)
            all_metadata.append({"page": p["page"], "source": "海龟交易法则"})

    print(f"共生成 {len(all_chunks)} 个文本块")

    print("正在加载嵌入模型...")
    # 使用多语言模型，对中文支持良好
    embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    print("正在生成嵌入向量并存入 ChromaDB...")
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))

    # 如果已存在 collection 则先删除重建
    try:
        client.delete_collection("turtle_trading")
    except Exception:
        pass

    collection = client.create_collection(
        name="turtle_trading",
        metadata={"description": "海龟交易法则知识库"},
    )

    # 分批处理，避免内存峰值过大
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch_chunks = all_chunks[i : i + batch_size]
        batch_meta = all_metadata[i : i + batch_size]
        embeddings = embed_model.encode(batch_chunks, show_progress_bar=False).tolist()

        collection.add(
            ids=[f"chunk_{j}" for j in range(i, i + len(batch_chunks))],
            documents=batch_chunks,
            metadatas=batch_meta,
            embeddings=embeddings,
        )
        print(f"  {i + len(batch_chunks)}/{len(all_chunks)} 块完成")

    print(f"\n知识库接入完成！共 {collection.count()} 个文本块已存入 ChromaDB")
    print(f"存储路径: {CHROMA_DB_DIR}")


if __name__ == "__main__":
    build_vectorstore()
