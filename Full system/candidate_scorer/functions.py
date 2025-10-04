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
import ast

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

def _get_field(d: dict, *candidates, default=None):
    """Return first found field in dict from candidates, else default."""
    if not isinstance(d, dict):
        return default
    for c in candidates:
        if c in d and d.get(c) is not None:
            return d.get(c)
    return default

def flatten_experience_items(exp_list) -> List[str]:
    """
    Accepts many shapes:
      - list of dicts with keys like role/title, company, start_end/duration, skills, description
      - dict with 'items': [...]
      - plain list of strings
    """
    out = []
    if not exp_list:
        return out

    # if a dict containing items
    if isinstance(exp_list, dict):
        maybe_items = exp_list.get("items") or exp_list.get("positions") or exp_list.get("roles")
        if maybe_items:
            return flatten_experience_items(maybe_items)
        # if keyed by date or company, flatten values
        for v in exp_list.values():
            if isinstance(v, (list, dict, str)):
                out.extend(flatten_experience_items(v))

        return out

    # if list or tuple
    if isinstance(exp_list, (list, tuple)):
        for e in exp_list:
            if isinstance(e, dict):
                role = _get_field(e, "role", "title", "position", "job_title") or ""
                company = _get_field(e, "company", "employer", "organisation", "organization") or ""
                period = _get_field(e, "start_end", "duration", "dates", "date") or ""
                skills = _get_field(e, "skills", "keywords", "stack", "technologies") or ""
                desc = _get_field(e, "description", "summary", "details", "about") or ""
                location = _get_field(e, "location", "place") or ""
                seg = " | ".join([p.strip() for p in [role, company, period, location, skills, desc] if p])
                if seg:
                    out.append(seg)
            elif isinstance(e, str):
                if e.strip():
                    out.append(e.strip())
            else:
                # fallback to string conversion
                out.append(str(e))
    else:
        # fallback for other single values
        out.append(str(exp_list))
    return out

def flatten_education(edu_list) -> str:
    """Accepts list of dicts or a dict or strings."""
    if not edu_list:
        return ""
    parts = []

    # if it's a dict containing entries
    if isinstance(edu_list, dict):
        maybe = edu_list.get("items") or edu_list.get("degrees") or edu_list.get("education")
        if maybe:
            return flatten_education(maybe)
        # else try to interpret dict as one record
        edu_list = [edu_list]

    for e in edu_list:
        if isinstance(e, dict):
            inst = _get_field(e, "institution", "school", "college", "university", default="") or ""
            field = _get_field(e, "field_of_study", "major", "degree", default="") or ""
            period = _get_field(e, "start_end", "dates", "duration") or ""
            grade = _get_field(e, "grade", "score", "gpa") or ""
            desc = _get_field(e, "description", "notes", "summary") or ""
            seg = " | ".join([x.strip() for x in [inst, field, period, grade, desc] if x])
            if seg:
                parts.append(seg)
        elif isinstance(e, str):
            parts.append(e.strip())
        else:
            parts.append(str(e))
    return " \n ".join(parts)

def flatten_skills(sk):
    """Accept many shapes for skills."""
    if not sk:
        return ""
    if isinstance(sk, list):
        return " ; ".join(map(str, sk))
    if isinstance(sk, dict):
        # dict could be {skill: level} or categories
        if all(isinstance(v, (int, float, str)) for v in sk.values()):
            return " ; ".join([f"{k}:{v}" for k, v in sk.items()])
        # otherwise flatten nested lists
        out = []
        for v in sk.values():
            if isinstance(v, (list, tuple)):
                out.extend(map(str, v))
            else:
                out.append(str(v))
        return " ; ".join(out)
    return str(sk)

def parse_languages(langs_field) -> List[Dict]:
    out = []
    if not langs_field:
        return out
    if isinstance(langs_field, list):
        for it in langs_field:
            if isinstance(it, dict):
                name = _get_field(it, "language", "name", default="") or ""
                lvl = _get_field(it, "level", "proficiency", default=0)
                # normalize level
                try:
                    lvl = float(lvl)
                except Exception:
                    mp = {"native": 2, "mother tongue": 2, "fluent": 2, "advanced": 2, "intermediate": 1, "basic": 0}
                    lvl = mp.get(str(lvl).lower(), 1.0)
                out.append({"language": str(name).strip(), "level": float(max(0.0, min(2.0, lvl)))})
            elif isinstance(it, str):
                # try to split "English:2" or "English - fluent"
                parts = re.split(r"[:\-–]", it, maxsplit=1)
                name = parts[0].strip()
                lvl = 1.0
                if len(parts) > 1:
                    try:
                        lvl = float(parts[1].strip())
                    except Exception:
                        s = parts[1].strip().lower()
                        mp = {"native": 2, "fluent": 2, "advanced": 2, "intermediate": 1, "basic": 0}
                        lvl = mp.get(s, 1.0)
                out.append({"language": name, "level": float(max(0.0, min(2.0, lvl)))})
    elif isinstance(langs_field, dict):
        for k, v in langs_field.items():
            try:
                lv = float(v)
            except Exception:
                s = str(v).lower()
                mp = {"native": 2, "fluent": 2, "advanced": 2, "intermediate": 1, "basic": 0}
                lv = mp.get(s, 1.0)
            out.append({"language": k.strip(), "level": float(max(0.0, min(2.0, lv)))})
    else:
        # single string like "English, French"
        if isinstance(langs_field, str):
            for lang in re.split(r",|\||;", langs_field):
                ln = lang.strip()
                if ln:
                    out.append({"language": ln, "level": 1.0})
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
        if self.index.ntotal == 0:
            return []
        D, I = self.index.search(q_emb.astype("float32"), top_k)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            meta = self.id_to_meta.get(int(idx), {})
            results.append({"score": float(score), "meta": meta})
        return results

# ---------------- PHelper functions ----------------

def try_parse_maybe_string(obj):
    """If obj is a string that looks like a Python/JSON literal, try to parse it."""
    if not isinstance(obj, str):
        return obj
    s = obj.strip()
    if not s:
        return obj
    if s[0] in "{[" and s[-1] in "}]" :
        try:
            return ast.literal_eval(s)
        except Exception:
            try:
                return json.loads(s)
            except Exception:
                return obj
    return obj

def extract_profiles_from_blob(blob):
    """Return a list of profile dict(s) extracted from various wrapping formats."""
    profiles = []
    if isinstance(blob, dict):
        # case: results list
        if "results" in blob and isinstance(blob["results"], list):
            for r in blob["results"]:
                r2 = try_parse_maybe_string(r)
                if isinstance(r2, dict):
                    # unwrap nested keys if present
                    for nk in ("profile", "person", "candidate"):
                        if nk in r2 and isinstance(r2[nk], dict):
                            profiles.append(r2[nk])
                            break
                    else:
                        profiles.append(r2)
            return profiles
        # case: result may be a dict or stringified dict
        if "result" in blob:
            inner = try_parse_maybe_string(blob["result"])
            if isinstance(inner, dict):
                # merge useful top-level fields
                for k in ("url", "candidate_id", "profile_url", "id"):
                    if k in blob and k not in inner:
                        inner[k] = blob[k]
                profiles.append(inner)
                return profiles
        # otherwise treat the dict itself as a profile
        profiles.append(blob)
    elif isinstance(blob, list):
        for item in blob:
            item2 = try_parse_maybe_string(item)
            if isinstance(item2, dict):
                profiles.append(item2)
    else:
        p = try_parse_maybe_string(blob)
        if isinstance(p, dict):
            profiles.append(p)
    return profiles

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

    def _extract_candidate_id(self, profile: dict, path: str) -> str:
        # try common id fields, else fallback to filename
        cid = _get_field(profile, "id", "candidate_id", "profile_id", "uid", "user_id")
        if cid:
            return str(cid)
        # try url or linkedin
        url = _get_field(profile, "url", "linkedin", "linkedin_url", "profile_url")
        if url:
            return str(url)
        return os.path.splitext(os.path.basename(path))[0]


    def add_profiles(self, json_paths: List[str]):
        skills_texts, skills_meta = [], []
        exp_texts, exp_meta = [], []
        edu_texts, edu_meta = [], []

        for path in json_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                print(f"[WARN] failed to load {path}: {e}")
                continue

            profile_blobs = extract_profiles_from_blob(raw)
            if not profile_blobs:
                # fallback: if nothing found, try treating the whole file as one profile dict/string
                parsed = try_parse_maybe_string(raw)
                if isinstance(parsed, dict):
                    profile_blobs = [parsed]
            if not profile_blobs:
                print(f"[WARN] no profile objects found in {path}")
                continue

            for profile in profile_blobs:
                # get candidate id (keep your existing _extract_candidate_id if present)
                cid = self._extract_candidate_id(profile, path) if hasattr(self, "_extract_candidate_id") else (
                    profile.get("id") or profile.get("candidate_id") or profile.get("profile_url") or os.path.splitext(os.path.basename(path))[0])
                self.profiles[cid] = profile

                about = profile.get("summary") or profile.get("about") or profile.get("headline") or ""

                # Skills
                sk_src = (profile.get("skills") or profile.get("skill") or profile.get("skill_set") or
                        profile.get("keywords") or profile.get("skills_list"))
                sk_txt = flatten_skills(sk_src) if sk_src is not None else ""
                if not sk_txt:
                    # fallback: look for long text fields
                    for cand in ("summary","about","description","details"):
                        c = profile.get(cand)
                        if isinstance(c, str) and len(c) > 10:
                            sk_txt = c
                            break
                if about and about not in sk_txt:
                    sk_txt = (about + "\n" + sk_txt) if sk_txt else about

                if sk_txt:
                    skills_texts.append(normalize_text(sk_txt))
                    skills_meta.append({"candidate_id": cid, "section": "skills", "excerpt": sk_txt[:300], "origin": path})

                # Experience
                exp_src = (profile.get("experience") or profile.get("work_experience") or
                        profile.get("positions") or profile.get("jobs") or [])
                exp_items = flatten_experience_items(exp_src or [])
                for i, it in enumerate(exp_items):
                    exp_texts.append(normalize_text(it))
                    exp_meta.append({"candidate_id": cid, "section": "experience", "excerpt": it[:300], "origin": path, "item_idx": i})

                # Education
                edu_src = profile.get("education") or profile.get("studies") or profile.get("education_history") or []
                edu_txt = flatten_education(edu_src or [])
                if edu_txt:
                    edu_texts.append(normalize_text(edu_txt))
                    edu_meta.append({"candidate_id": cid, "section": "education", "excerpt": edu_txt[:300], "origin": path})

        # finally embed and add to indices (unchanged)
        if skills_texts:
            emb = self._embed_texts(skills_texts)
            self.skills_idx.add(emb, skills_meta)
        if exp_texts:
            emb = self._embed_texts(exp_texts)
            self.exp_idx.add(emb, exp_meta)
        if edu_texts:
            emb = self._embed_texts(edu_texts)
            self.edu_idx.add(emb, edu_meta)
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
                cid = self._extract_candidate_id(profile, path)
                self.profiles[cid] = profile

                # collect a short summary/about if present to feed into skills/summary
                about = _get_field(profile, "summary", "about", "headline", default="") or ""

                # Skills (many possible keys)
                sk_src = _get_field(profile, "skills", "skill", "skill_set", "keywords", "skills_list", default=None)
                sk_txt = flatten_skills(sk_src) if sk_src is not None else ""
                # as fallback, try to derive skills from a single string such as a 'skills' long string
                if not sk_txt:
                    # sometimes skills are in a single string field or mixed into 'profile' or 'details'
                    candidates = [profile.get("skills"), profile.get("summary"), profile.get("about"), profile.get("description"), profile.get("details")]
                    for c in candidates:
                        if isinstance(c, str) and len(c) > 10:
                            sk_txt = c
                            break
                # add about if present and not duplicate
                if about and about not in sk_txt:
                    if sk_txt:
                        sk_txt = about + " \n " + sk_txt
                    else:
                        sk_txt = about

                if sk_txt:
                    skills_texts.append(normalize_text(sk_txt))
                    skills_meta.append({"candidate_id": cid, "section": "skills", "excerpt": (sk_txt[:300] if isinstance(sk_txt, str) else str(sk_txt)) , "origin": path})

                # Experience
                exp_src = _get_field(profile, "experience", "work_experience", "positions", "jobs", default=[])
                exp_items = flatten_experience_items(exp_src or [])
                for i, it in enumerate(exp_items):
                    exp_texts.append(normalize_text(it))
                    exp_meta.append({"candidate_id": cid, "section": "experience", "excerpt": it[:300], "origin": path, "item_idx": i})

                # Education
                edu_src = _get_field(profile, "education", "studies", "education_history", default=[])
                edu_txt = flatten_education(edu_src or [])
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
        langs = parse_languages(_get_field(profile, "languages", "language", "langs", default=[]))
        if not langs:
            return 0.0
        jt = normalize_text(job_text).lower()
        raw = 0.0
        for l in langs:
            name = (l.get("language") or "").lower()
            lvl = float(l.get("level") or 0.0)
            # if language name appears in job description give full weight, else partial
            raw += lvl if name and name in jt else 0.5 * lvl
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

    results = scorer.score(job_text)
    print("\nTop candidates:")
    for i, r in enumerate(results[:10]):
        print(f"{i+1}. {r['candidate_id']}  score={r['score']:.4f}  breakdown={r['breakdown']}")
