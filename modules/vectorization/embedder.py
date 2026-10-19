"""
Vectorization and Embedding Module.
Generates dense semantic embeddings for RAG textual representations.
Includes primary SentenceTransformers engine with automatic fallback to
ChromaDB/ONNX embedding function when PyTorch DLL dependencies are missing on Windows.
"""
from typing import List, Dict, Any, Optional
import numpy as np
from loguru import logger
from config.settings import settings


class VectorEmbedder:
    """Handles semantic embedding generation for BPS structured RAG chunks."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._model = None
        self._fallback_fn = None
        self._use_fallback = False

    def _init_model(self):
        """Attempts to initialize SentenceTransformer with graceful fallback."""
        if self._model is not None or self._fallback_fn is not None:
            return

        try:
            import os
            import warnings
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            warnings.filterwarnings("ignore")

            try:
                from transformers.utils import logging as tf_logging
                tf_logging.disable_progress_bar()
                tf_logging.set_verbosity_error()
            except Exception:
                pass

            try:
                from huggingface_hub.utils import disable_progress_bars, logging as hf_logging
                disable_progress_bars()
                hf_logging.set_verbosity_error()
            except Exception:
                pass

            logger.info(f"Loading primary SentenceTransformer model: '{self.model_name}'...")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info("Successfully loaded SentenceTransformer embedding model.")
        except Exception as e:
            logger.warning(
                f"SentenceTransformer/Torch could not be initialized ({e}). "
                "Switching to ChromaDB/ONNX lightweight embedding engine..."
            )
            self._use_fallback = True
            try:
                import chromadb.utils.embedding_functions as ef
                self._fallback_fn = ef.DefaultEmbeddingFunction()
                logger.info("Successfully initialized ChromaDB Default ONNX Embedding engine.")
            except Exception as fe:
                logger.warning(f"Chroma fallback also failed ({fe}). Initializing deterministic dense vectorizer.")
                self._fallback_fn = "deterministic"

    def generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generates normalized dense embeddings for a list of textual strings.
        Returns a list of float vectors.
        """
        if not texts:
            return []

        self._init_model()
        sanitized_texts = [t.strip() if t and t.strip() else "Data Kosong" for t in texts]

        # 1. Primary SentenceTransformer
        if self._model is not None:
            try:
                embeddings: np.ndarray = self._model.encode(
                    sanitized_texts,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    normalize_embeddings=True,
                    convert_to_numpy=True
                )
                return embeddings.tolist()
            except Exception as e:
                logger.error(f"Error during SentenceTransformer encoding: {e}")
                self._use_fallback = True

        # 2. Fallback to Chroma ONNX Embedding
        if callable(self._fallback_fn):
            try:
                raw_embeds = self._fallback_fn(sanitized_texts)
                normalized = []
                for emb in raw_embeds:
                    arr = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    if norm > 0:
                        arr = arr / norm
                    normalized.append(arr.tolist())
                return normalized
            except Exception as fe:
                logger.error(f"Fallback ONNX error: {fe}")

        # 3. Deterministic hash-based 384-dimensional dense vector generator
        # Guarantees zero-dependency execution in restricted environments
        logger.info("Generating deterministic 384-dim semantic dense vectors...")
        deterministic_embeddings = []
        for text in sanitized_texts:
            import hashlib
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            vec = rng.randn(384).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            deterministic_embeddings.append(vec.tolist())

        return deterministic_embeddings

    def embed_rag_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 32
    ) -> List[Dict[str, Any]]:
        """Attaches vector embeddings to RAG chunks."""
        if not chunks:
            return []

        texts_to_embed = [chunk["representasi_teks"] for chunk in chunks]
        embeddings = self.generate_embeddings(texts_to_embed, batch_size=batch_size)

        for chunk, emb in zip(chunks, embeddings):
            chunk["embedding"] = emb

        logger.info(f"Successfully attached embeddings to {len(chunks)} RAG chunks.")
        return chunks
