from typing import Literal

from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    """Validated, reproducible analysis configuration (stored with the job)."""
    features: Literal["tfidf", "embeddings"] = "tfidf"
    algorithm: Literal["dbscan", "hdbscan", "kmeans"] = "dbscan"
    eps: float = Field(0.0, ge=0, le=2, description="0 = estimate from the k-distance knee")
    min_samples: int = Field(3, ge=1, le=100)
    min_cluster_size: int = Field(5, ge=2, le=1000)
    n_clusters: int = Field(0, ge=0, le=200)
    sim_threshold: float = Field(0.5, gt=0, le=1)
    contamination: float = Field(0.02, gt=0, le=0.5)
    z_threshold: float = Field(3.0, ge=1, le=10)
    lowercase: bool = False
    keep_stack_trace: bool = False
    run_evaluation: bool = True
    evaluation_max_unique: int = Field(4000, ge=100, le=20000)
    mask_rules: str | None = Field(None, description="comma list of: email,phone,token,password,apikey,ip,identifier or 'none'")
    disabled_rules: list[str] = []


class StartAnalysis(BaseModel):
    file_ids: list[int] = Field(min_length=1, max_length=20)
    config: AnalysisConfig = AnalysisConfig()


class LoadDataset(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ColumnMapping(BaseModel):
    mapping: dict[str, str | None] = Field(description="log field -> CSV header, e.g. {'timestamp': 'Event Time', 'message': 'Description'}")


class ExperimentRequest(BaseModel):
    eps: float = Field(0.0, ge=0, le=2)
    min_samples: int = Field(3, ge=1, le=100)
    min_cluster_size: int = Field(5, ge=2, le=1000)
    n_clusters: int = Field(0, ge=0, le=200)
    max_unique: int = Field(4000, ge=100, le=20000)
