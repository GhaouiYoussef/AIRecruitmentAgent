"""Scorer Tool Section"""
from typing import Dict, Optional, List
import os
import glob
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator as validator
from .functions import CandidateScorer, DEFAULT_WEIGHTS
# from starlette.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Scoring Request/Response Models
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FastAPI App Initialization
# ---------------------------------------------------------------------------
app = FastAPI(title="Candidate Scorer Tool", version="1.0.0")


class LoadProfilesRequest(BaseModel):
    json_folder: str = Field(..., description="Folder containing candidate JSON files")
    exp_agg: str = Field("sum_norm", description="Experience aggregation mode: sum | mean | sum_norm")
    reset: bool = Field(True, description="Reset the scorer and re-index from scratch")

    @validator("exp_agg")
    def _check_agg(cls, v: str) -> str:
        allowed = {"sum", "mean", "sum_norm"}
        if v not in allowed:
            raise ValueError(f"exp_agg must be one of {allowed}")
        return v


class ScoreRequest(BaseModel):
    job_text: str = Field(..., description="Job description text")
    weights: Optional[Dict[str, float]] = Field(None, description="Weights for sections")
    top_k_search: int = Field(200, ge=1, le=5000, description="FAISS top_k to search per section")

    @validator("weights")
    def _normalize_weights(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        if v is None:
            return None
        # Ensure only known keys are present; ignore extras
        cleaned = {k: float(v[k]) for k in ("experience", "skills", "education", "languages") if k in v}
        if not cleaned:
            return None
        return cleaned


class ScoreItem(BaseModel):
    candidate_id: str
    score: float
    breakdown: Dict[str, float]


class ScoreResponse(BaseModel):
    count: int
    results: List[ScoreItem]


# ---------------------------------------------------------------------------
# Global Scorer State
# ---------------------------------------------------------------------------
SCORER: Optional[CandidateScorer] = None


@app.get("/scorer_tool/health")
def health():
    global SCORER
    status = {
        "status": "ok",
        "indexed_profiles": 0 if SCORER is None else len(SCORER.profiles),
        "exp_agg_mode": None if SCORER is None else SCORER.exp_agg_mode,
    }
    return status


@app.post("/scorer_tool/load_profiles")
def load_profiles(req: LoadProfilesRequest):
    global SCORER

    json_folder = req.json_folder
    if not os.path.isabs(json_folder):
        # Resolve relative to current working directory
        json_folder = os.path.abspath(os.path.join(os.getcwd(), json_folder))

    if not os.path.isdir(json_folder):
        raise HTTPException(status_code=400, detail=f"json_folder not found: {json_folder}")

    files = glob.glob(os.path.join(json_folder, "*.json"))
    if not files:
        raise HTTPException(status_code=400, detail=f"No JSON files found in {json_folder}")

    if req.reset or SCORER is None:
        SCORER = CandidateScorer(exp_agg_mode=req.exp_agg)
    else:
        # If already initialized but exp_agg changes, recreate to avoid confusion
        if SCORER.exp_agg_mode != req.exp_agg:
            SCORER = CandidateScorer(exp_agg_mode=req.exp_agg)

    SCORER.add_profiles(files)
    return {
        "indexed_profiles": len(SCORER.profiles),
        "source": json_folder,
        "files_added": len(files),
        "exp_agg_mode": SCORER.exp_agg_mode,
    }


@app.post("/scorer_tool/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    global SCORER
    if SCORER is None or len(SCORER.profiles) == 0:
        raise HTTPException(status_code=400, detail="No profiles indexed. Call /load_profiles first.")

    weights = req.weights if req.weights is not None else DEFAULT_WEIGHTS
    try:
        results = SCORER.score(req.job_text, weights=weights, top_k_search=req.top_k_search)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    items = [ScoreItem(**r) for r in results]
    return ScoreResponse(count=len(items), results=items)
