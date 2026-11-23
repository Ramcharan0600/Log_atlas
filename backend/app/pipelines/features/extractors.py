"""Feature representations: lexical (TF-IDF) and semantic (Sentence-Transformer embeddings), with disk caching.

Both return L2-normalised dense matrices so cosine distance == euclidean distance (up to a monotone map) and the same
clustering code works for either representation. TF-IDF is reduced with truncated SVD (LSA) to keep clustering tractable.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize as l2norm

from app.core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class FeatureResult:
    matrix: np.ndarray            # (n, d) L2-normalised, dense
    backend: str                  # "tfidf-word" | "tfidf-word+char" | "sbert:all-MiniLM-L6-v2" | "lsa-fallback"
    seconds: float
    dim: int
    note: str = ""
    sparse_tfidf: sparse.csr_matrix | None = None
    vectorizer: TfidfVectorizer | None = None


def tfidf_features(texts: list[str], mode: str = "word+char", svd_dim: int = 100, max_features: int = 20000,
                   ngram_range: tuple[int, int] = (1, 2), char_range: tuple[int, int] = (3, 5)) -> FeatureResult:
    """mode: 'word' (word n-grams) | 'char' (char n-grams) | 'word+char'."""
    t0 = time.perf_counter()
    mats, vecs = [], []
    if mode in ("word", "word+char"):
        v = TfidfVectorizer(ngram_range=ngram_range, token_pattern=r"(?u)<[A-Z_]+>|\b\w[\w.-]*\b", lowercase=True, sublinear_tf=True,
                            max_features=max_features, min_df=1)
        mats.append(v.fit_transform(texts)); vecs.append(v)
    if mode in ("char", "word+char"):
        v = TfidfVectorizer(analyzer="char_wb", ngram_range=char_range, lowercase=True, sublinear_tf=True, max_features=max_features, min_df=1)
        mats.append(v.fit_transform(texts)); vecs.append(v)
    if not mats:
        raise ValueError(f"unknown tfidf mode '{mode}'")
    sp = l2norm(sparse.hstack(mats).tocsr()) if len(mats) > 1 else mats[0].tocsr()
    k = min(svd_dim, sp.shape[0] - 1, sp.shape[1] - 1)
    if k >= 2:
        dense = TruncatedSVD(n_components=k, random_state=42).fit_transform(sp)
    else:
        dense = sp.toarray()
    dense = l2norm(dense)
    return FeatureResult(dense.astype(np.float32), f"tfidf-{mode}", time.perf_counter() - t0, dense.shape[1], sparse_tfidf=sp, vectorizer=vecs[0])


_ST_MODEL = {}


def _load_st(name: str):
    if name not in _ST_MODEL:
        from sentence_transformers import SentenceTransformer  # heavy import, only on demand
        tok = get_settings().hf_token or None
        _ST_MODEL[name] = SentenceTransformer(name, token=tok)
    return _ST_MODEL[name]


def _cache_path(texts: list[str], model: str) -> Path:
    h = hashlib.sha1(("\n".join(texts) + "|" + model).encode("utf-8", "ignore")).hexdigest()[:20]
    return Path(get_settings().cache_dir) / f"emb_{h}.npy"


def embedding_features(texts: list[str], model: str | None = None, batch_size: int = 64, use_cache: bool = True) -> FeatureResult:
    """Sentence-Transformer embeddings (batched, cached). If the model cannot be loaded (offline / not installed),
    falls back to LSA over character n-grams and says so loudly in `backend` + `note` - results are never mislabeled."""
    st = get_settings()
    model = model or st.embedding_model
    t0 = time.perf_counter()
    cp = _cache_path(texts, model)
    if use_cache and cp.exists():
        try:
            m = np.load(cp)
            if m.shape[0] == len(texts):
                return FeatureResult(m, f"sbert:{model}", time.perf_counter() - t0, m.shape[1], note="loaded from cache")
        except Exception:  # corrupt cache -> recompute
            pass
    if st.embeddings_enabled:
        try:
            enc = _load_st(model)
            m = enc.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True).astype(np.float32)
            if use_cache:
                np.save(cp, m)
            return FeatureResult(m, f"sbert:{model}", time.perf_counter() - t0, m.shape[1])
        except Exception as e:  # noqa: BLE001 - any load/network failure must degrade gracefully
            log.warning("Sentence-Transformers unavailable (%s: %s); using LSA fallback", type(e).__name__, str(e)[:120])
            note = f"Sentence-Transformers model '{model}' could not be loaded ({type(e).__name__}); LSA character-n-gram fallback used instead."
    else:
        note = "Embeddings disabled by configuration; LSA character-n-gram fallback used instead."
    fb = tfidf_features(texts, "char", svd_dim=128)
    return FeatureResult(fb.matrix, "lsa-fallback", time.perf_counter() - t0, fb.dim, note=note)


def build_features(texts: list[str], method: str, **kw) -> FeatureResult:
    if method.startswith("tfidf"):
        mode = method.split("-", 1)[1] if "-" in method else "word+char"
        return tfidf_features(texts, mode, svd_dim=kw.get("svd_dim", 100))
    if method in ("embeddings", "sbert"):
        return embedding_features(texts, kw.get("model"))
    raise ValueError(f"unknown feature method '{method}'")


def similarity_matrix(X: np.ndarray, top_k: int = 5) -> np.ndarray:
    """Cosine-similarity of L2-normalised rows (dense; use only for small n such as cluster centroids)."""
    return X @ X.T
