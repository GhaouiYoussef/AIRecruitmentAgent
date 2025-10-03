#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import json
import glob
import re
import math
import argparse
from typing import List, Dict, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

# ---------------- Config ----------------
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 64
DEFAULT_WEIGHTS = {"experience": 0.4, "skills": 0.4, "education": 0.2, "languages": 0.1}

# ---------------- Utility Functions ----------------
def normalize_text(s: Optional[str]) -> str:
    s = (s or "").strip()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def flatten_experience_items(exp_list) -> List[str]:
    out = []
    if not exp_list:
        return out
    for e in exp_list:
        if isinstance(e, dict):
            role = e.get("role") or ""
            company = e.get("company") or ""
            period = e.get("start_end") or e.get("duration") or ""
            skills = e.get("skills") or ""
            desc = e.get("description") or ""
            seg = " | ".join([p.strip() for p in [role, company, period, skills, desc] if p])
            if seg:
                out.append(seg)
        else:
            out.append(str(e))
    return out

def flatten_education(edu_list) -> str:
    if not edu_list:
        return ""
    parts = []
    for e in edu_list:
        if isinstance(e, dict):
            inst = e.get("institution") or e.get("school") or ""
            field = e.get("field_of_study") or e.get("degree") or ""
            desc = e.get("description") or ""
            seg = " | ".join([x.strip() for x in [inst, field, desc] if x])
            if seg:
                parts.append(seg)
        else:
            parts.append(str(e))
    return " \n ".join(parts)

def flatten_skills(sk):
    if not sk:
        return ""
    if isinstance(sk, list):
        return " ; ".join(map(str, sk))
    return str(sk)

def parse_languages(langs_field) -> List[Dict]:
    out = []
    if not langs_field:
        return out
    if isinstance(langs_field, list):
        for it in langs_field:
            if isinstance(it, dict):
                name = it.get("language") or ""
                lvl = it.get("level", 0)
                try:
                    lvl = float(lvl)
                except Exception:
                    mp = {"native": 2, "fluent": 2, "advanced": 2, "intermediate": 1, "basic": 0}
                    lvl = mp.get(str(lvl).lower(), 0)
                out.append({"language": str(name).strip(), "level": float(max(0.0, min(2.0, lvl)))})
            elif isinstance(it, str):
                out.append({"language": it.strip(), "level": 1.0})
    elif isinstance(langs_field, dict):
        for k, v in langs_field.items():
            try:
                lv = float(v)
            except Exception:
                lv = 1.0
            out.append({"language": k.strip(), "level": float(max(0.0, min(2.0, lv)))})
    return out

# ---------------- Indexing Classes ----------------
class SectionIndex:
    def __init__(self, dim: int):
        base = faiss.IndexFlatIP(dim)
        self.index = faiss.IndexIDMap(base)
        self.id_to_meta = {}
        self.next_id = 0

    def add(self, embeddings: np.ndarray, metas: List[dict]):
        n = embeddings.shape[0]
        if n == 0:
            return 0
        ids = np.arange(self.next_id, self.next_id + n).astype("int64")
        embeddings = np.ascontiguousarray(embeddings.astype("float32"))
        self.index.add_with_ids(embeddings, ids)
        for i, _id in enumerate(ids):
            self.id_to_meta[int(_id)] = metas[i]
        self.next_id += n
        return n

    def search(self, q_emb: np.ndarray, top_k: int = 10):
        D, I = self.index.search(q_emb.astype("float32"), top_k)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            meta = self.id_to_meta.get(int(idx), {})
            results.append({"score": float(score), "meta": meta})
        return results

# ---------------- Candidate Scorer ----------------
class CandidateScorer:
    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = BATCH_SIZE, exp_agg_mode: str = "sum_norm"):
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.batch_size = batch_size

        self.skills_idx = SectionIndex(self.dim)
        self.exp_idx = SectionIndex(self.dim)
        self.edu_idx = SectionIndex(self.dim)
        self.profiles = {}
        self.exp_agg_mode = exp_agg_mode

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        emb = self.model.encode(texts, batch_size=self.batch_size, convert_to_numpy=True, show_progress_bar=False)
        faiss.normalize_L2(emb)
        return emb

    def add_profiles(self, json_paths: List[str]):
        skills_texts, skills_meta = [], []
        exp_texts, exp_meta = [], []
        edu_texts, edu_meta = [], []

        for path in json_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
            except Exception as e:
                print(f"[WARN] failed to load {path}: {e}")
                continue
            cid = profile.get("id") or os.path.splitext(os.path.basename(path))[0]
            self.profiles[cid] = profile

            # Skills
            sk_txt = flatten_skills(profile.get("skills") or profile.get("skill"))
            if sk_txt:
                skills_texts.append(normalize_text(sk_txt))
                skills_meta.append({"candidate_id": cid, "section": "skills", "excerpt": sk_txt[:300], "origin": path})

            # Experience
            exp_items = flatten_experience_items(profile.get("experience") or [])
            for i, it in enumerate(exp_items):
                exp_texts.append(normalize_text(it))
                exp_meta.append({"candidate_id": cid, "section": "experience", "excerpt": it[:300], "origin": path, "item_idx": i})

            # Education
            edu_txt = flatten_education(profile.get("education") or [])
            if edu_txt:
                edu_texts.append(normalize_text(edu_txt))
                edu_meta.append({"candidate_id": cid, "section": "education", "excerpt": edu_txt[:300], "origin": path})

        if skills_texts:
            emb = self._embed_texts(skills_texts)
            self.skills_idx.add(emb, skills_meta)
        if exp_texts:
            emb = self._embed_texts(exp_texts)
            self.exp_idx.add(emb, exp_meta)
        if edu_texts:
            emb = self._embed_texts(edu_texts)
            self.edu_idx.add(emb, edu_meta)

    # ---------------- Scoring Methods ----------------
    def _compute_experience_scores(self, job_text: str, top_k: int = 200) -> Dict[str, float]:
        q_emb = self.model.encode([normalize_text(job_text)], convert_to_numpy=True)
        faiss.normalize_L2(q_emb)
        results = self.exp_idx.search(q_emb, top_k=top_k)
        per_candidate_entries = {}
        for r in results:
            cid = r["meta"].get("candidate_id")
            sc = r["score"]
            if not cid:
                continue
            per_candidate_entries.setdefault(cid, []).append(float(sc))
        aggregated = {}
        for cid, scores in per_candidate_entries.items():
            n = len(scores)
            ssum = sum(scores)
            if self.exp_agg_mode == "sum":
                agg = ssum
            elif self.exp_agg_mode == "mean":
                agg = ssum / n if n > 0 else 0.0
            else:  # sum_norm
                agg = ssum / (1.0 + math.log(1.0 + n))
            agg = max(0.0, min(1.0, agg))
            aggregated[cid] = agg
        return aggregated

    def _compute_section_best(self, job_text: str, section_idx: SectionIndex, top_k: int = 200) -> Dict[str, float]:
        q_emb = self.model.encode([normalize_text(job_text)], convert_to_numpy=True)
        faiss.normalize_L2(q_emb)
        results = section_idx.search(q_emb, top_k=top_k)
        by_cand = {}
        for r in results:
            cid = r["meta"].get("candidate_id")
            sc = r["score"]
            if cid:
                by_cand[cid] = max(by_cand.get(cid, 0.0), sc)
        for c in list(by_cand.keys()):
            by_cand[c] = max(0.0, min(1.0, by_cand[c]))
        return by_cand

    def _language_score(self, profile: dict, job_text: str) -> float:
        langs = parse_languages(profile.get("languages") or [])
        if not langs:
            return 0.0
        jt = normalize_text(job_text).lower()
        raw = 0.0
        for l in langs:
            name = (l.get("language") or "").lower()
            lvl = float(l.get("level") or 0.0)
            raw += lvl if name in jt else 0.5 * lvl
        denom = 2.0 * len(langs)
        return max(0.0, min(1.0, raw / denom)) if denom > 0 else 0.0

    def score(self, job_text: str, weights: Optional[Dict[str, float]] = None, top_k_search: int = 200) -> List[dict]:
        if weights is None:
            weights = DEFAULT_WEIGHTS
        s = sum(weights.values())
        norm_w = {k: float(v)/s for k, v in weights.items()}

        exp_scores = self._compute_experience_scores(job_text, top_k=top_k_search)
        skills_scores = self._compute_section_best(job_text, self.skills_idx, top_k=top_k_search)
        edu_scores = self._compute_section_best(job_text, self.edu_idx, top_k=top_k_search)

        out = []
        for cid, profile in self.profiles.items():
            se = exp_scores.get(cid, 0.0)
            ss = skills_scores.get(cid, 0.0)
            sedu = edu_scores.get(cid, 0.0)
            lscore = self._language_score(profile, job_text)
            total = (norm_w.get("experience", 0.0)*se +
                     norm_w.get("skills", 0.0)*ss +
                     norm_w.get("education", 0.0)*sedu +
                     norm_w.get("languages", 0.0)*lscore)
            out.append({"candidate_id": cid,
                        "score": float(total),
                        "breakdown": {"experience": float(se), "skills": float(ss), "education": float(sedu), "languages": float(lscore)}})
        return sorted(out, key=lambda x: x["score"], reverse=True)

# ---------------- Terminal Runnable ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Candidate Scoring Tool")
    parser.add_argument("--json_folder", type=str, default="../json_candids", help="Folder with candidate JSON files")
    parser.add_argument("--job", type=str, required=True, help="Job description text")
    parser.add_argument("--exp_agg", type=str, default="sum_norm", choices=["sum", "mean", "sum_norm"], help="Experience aggregation mode")
    args = parser.parse_args()

    # Support --job @path/to/file to read job description from a file
    if isinstance(args.job, str) and args.job.startswith('@'):
        job_path = args.job[1:]
        # If relative path given, resolve relative to current working directory
        if not os.path.isabs(job_path):
            job_path = os.path.join(os.getcwd(), job_path)
        try:
            with open(job_path, 'r', encoding='utf-8') as f:
                job_text = f.read()
        except Exception as e:
            print(f"Error: cannot read job file '{job_path}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        job_text = args.job
        
    files = glob.glob(os.path.join(args.json_folder, "*.json"))
    if not files:
        print("No JSON files found at", args.json_folder)
        raise SystemExit(1)

    scorer = CandidateScorer(exp_agg_mode=args.exp_agg)
    print("Indexing", len(files), "profiles...")
    scorer.add_profiles(files)
    print("Indexed profiles:", len(scorer.profiles))

    results = scorer.score(args.job)
    print("\nTop candidates:")
    for i, r in enumerate(results[:10]):
        print(f"{i+1}. {r['candidate_id']}  score={r['score']:.4f}  breakdown={r['breakdown']}")
