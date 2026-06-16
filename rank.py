#!/usr/bin/env python3
import json
import csv
import argparse
from datetime import datetime

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return None

def generate_reasoning(candidate, rank):
    profile = candidate.get("profile", {})
    skills = candidate.get("skills", [])
    signals = candidate.get("redrob_signals", {})
    
    title = profile.get("current_title", "Engineer")
    exp = profile.get("years_of_experience", 0)
    loc = profile.get("location", "India")
    notice = signals.get("notice_period_days", 0)
    willing_reloc = signals.get("willing_to_relocate", False)
    
    # Identify matched core skills
    vec_dbs = {"faiss", "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "chroma"}
    emb_retrieval = {"sentence-transformers", "bge", "e5", "openai embeddings", "cohere embeddings", "transformers", "huggingface", "embeddings"}
    nlp_ir = {"nlp", "natural language processing", "information retrieval", "search", "ranking", "re-ranking", "rag", "retrieval-augmented generation", "semantic search"}
    
    matched_skills = []
    for s in skills:
        s_name = s.get("name", "").lower()
        if any(db in s_name for db in vec_dbs) or any(emb in s_name for emb in emb_retrieval) or any(nlp in s_name for nlp in nlp_ir):
            matched_skills.append(s.get("name"))
            
    matched_skills_str = ", ".join(matched_skills[:3]) if matched_skills else "search architectures"
    
    # Use deterministic hash of candidate_id to introduce variation in template structure
    cid_hash = hash(candidate.get("candidate_id", ""))
    
    verb_options = [
        "demonstrating strong expertise in",
        "with solid hands-on experience in",
        "exhibiting proven capability in",
        "with a clear background in"
    ]
    verb = verb_options[cid_hash % len(verb_options)]
    
    role_options = [
        f"working as a {title}",
        f"shipped relevant systems as a {title}",
        f"currently positioned as a {title}"
    ]
    role_desc = role_options[cid_hash % len(role_options)]
    
    # Dynamic template based on rank
    if rank <= 10:
        lead = f"Outstanding match for founding team with {exp:.1f} years of experience in ML/AI."
        body = f"Brings high-quality production experience, {verb} {matched_skills_str} while {role_desc}."
    elif rank <= 50:
        lead = f"Strong candidate with {exp:.1f} years of experience in NLP/IR systems."
        body = f"Shows solid background, {verb} {matched_skills_str} while {role_desc}."
    else:
        lead = f"Good technical alignment with {exp:.1f} years of experience."
        body = f"Matches backend and IR requirements, {verb} {matched_skills_str} while {role_desc}."
        
    # Gaps check
    gaps = []
    if notice > 60:
        gaps.append(f"notice period of {notice} days is longer than target")
    if "pune" not in loc.lower() and "noida" not in loc.lower():
        if willing_reloc:
            gaps.append(f"willing to relocate from {loc}")
        else:
            gaps.append(f"hybrid relocation from {loc} needed")
            
    if gaps:
        gap_str = "; ".join(gaps)
        if rank <= 10:
            return f"{lead} {body}; note that {gap_str}."
        else:
            return f"{lead} {body} ({gap_str})."
    else:
        return f"{lead} {body}."

def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Senior AI Engineer JD.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl")
    parser.add_argument("--out", required=True, help="Path to output CSV file")
    args = parser.parse_args()
    
    print(f"Reading candidates from {args.candidates}...")
    
    # Services/Consulting companies
    services_companies = {
        "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
        "hcl", "tech mahindra", "l&t", "lnt", "mindtree", "mphasis",
        "tata consultancy services", "wipro technologies", "infosys limited",
        "cognizant technology solutions", "capgemini services"
    }
    
    today = datetime(2026, 6, 16)
    scored_candidates = []
    
    with open(args.candidates, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            candidate = json.loads(line)
            cid = candidate["candidate_id"]
            
            profile = candidate.get("profile", {})
            skills = candidate.get("skills", [])
            history = candidate.get("career_history", [])
            education = candidate.get("education", [])
            signals = candidate.get("redrob_signals", {})
            
            # --- HONEYPOT FILTER ---
            is_honeypot = False
            
            # 1. Zero duration expert skills
            expert_zero_dur = [s for s in skills if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0]
            if len(expert_zero_dur) >= 2:
                is_honeypot = True
                
            # 2. Date/duration inconsistencies in career history
            oldest_start = None
            years_of_exp = profile.get("years_of_experience", 0)
            
            for job in history:
                start_str = job.get("start_date")
                end_str = job.get("end_date")
                dur_months = job.get("duration_months", 0)
                
                start_dt = parse_date(start_str)
                if start_dt:
                    if oldest_start is None or start_dt < oldest_start:
                        oldest_start = start_dt
                        
                    end_dt = parse_date(end_str) if end_str else today
                    
                    if end_dt:
                        delta_months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
                        if dur_months > delta_months + 2:
                            is_honeypot = True
                        if end_str and end_dt < start_dt:
                            is_honeypot = True
                            
                dur_years = dur_months / 12.0
                if dur_years > years_of_exp + 0.1:
                    is_honeypot = True
            
            # 3. Experience vs career span
            if oldest_start:
                career_span_years = ((today - oldest_start).days) / 365.25
                if years_of_exp > career_span_years + 1.0:
                    is_honeypot = True
            
            # 4. Education end_year before start_year
            for edu in education:
                start_yr = edu.get("start_year")
                end_yr = edu.get("end_year")
                if start_yr and end_yr and end_yr < start_yr:
                    is_honeypot = True
                    
            if is_honeypot:
                continue
                
            # --- SCORING LOGIC ---
            score = 0.0
            
            # 1. Experience Years Fit
            exp_score = 0.0
            if 6.0 <= years_of_exp <= 8.0:
                exp_score = 10.0
            elif 5.0 <= years_of_exp <= 9.0:
                exp_score = 9.0
            elif 4.0 <= years_of_exp <= 10.0:
                exp_score = 7.0
            elif 3.0 <= years_of_exp <= 12.0:
                exp_score = 5.0
            elif 2.0 <= years_of_exp <= 15.0:
                exp_score = 2.0
            score += exp_score
            
            # 2. Company Type & Stability
            companies_worked = [job.get("company", "").lower() for job in history]
            total_jobs = len(companies_worked)
            services_jobs_count = sum(1 for c in companies_worked if any(sc in c for sc in services_companies))
            
            company_score = 10.0
            if total_jobs > 0:
                if services_jobs_count == total_jobs:
                    company_score = 0.0
                elif services_jobs_count > 0:
                    company_score = 5.0
                    
            # Job-hopping penalty
            avg_duration_months = sum(job.get("duration_months", 0) for job in history) / max(1, total_jobs)
            if avg_duration_months < 18.0 and total_jobs >= 3:
                company_score *= 0.6
            score += company_score
            
            # 3. Domain Fit
            headline = profile.get("headline", "").lower()
            current_title = profile.get("current_title", "").lower()
            summary = profile.get("summary", "").lower()
            
            core_keywords = ["search", "ranking", "retrieval", "nlp", "rag", "recommender", "recommendation", "embeddings", "vector search", "information retrieval"]
            title_keywords = ["machine learning", "ml", "ai", "data scientist", "applied scientist", "applied ml"]
            
            title_match = 0.0
            if any(k in current_title for k in core_keywords) or any(k in headline for k in core_keywords):
                title_match = 15.0
            elif any(k in current_title for k in title_keywords) or any(k in headline for k in title_keywords):
                title_match = 10.0
            elif "software engineer" in current_title or "backend engineer" in current_title:
                if any(k in summary for k in core_keywords):
                    title_match = 8.0
                elif any(k in summary for k in title_keywords):
                    title_match = 5.0
            score += title_match
            
            # Unwanted roles/domains
            unwanted_roles = ["marketing manager", "operations manager", "accountant", "hr manager", "customer support", "sales executive"]
            cv_keywords = ["computer vision", "image classification", "object detection", "yolo", "segmentation", "medical imaging"]
            speech_keywords = ["speech recognition", "tts", "asr", "whisper", "audio"]
            robotics_keywords = ["robotics", "ros", "slam", "control systems"]
            
            role_penalty = 1.0
            if any(k in current_title for k in unwanted_roles) or any(k in headline for k in unwanted_roles):
                role_penalty = 0.0
            elif (any(k in current_title for k in cv_keywords) or any(k in headline for k in cv_keywords)) and not any(k in current_title for k in core_keywords):
                role_penalty = 0.2
            elif (any(k in current_title for k in speech_keywords) or any(k in headline for k in speech_keywords)) and not any(k in current_title for k in core_keywords):
                role_penalty = 0.2
            elif (any(k in current_title for k in robotics_keywords) or any(k in headline for k in robotics_keywords)) and not any(k in current_title for k in core_keywords):
                role_penalty = 0.1
            score *= role_penalty
            
            # 4. Technical Skills Alignment
            skills_dict = {s.get("name", "").lower(): s for s in skills}
            vec_dbs = {"faiss", "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "chroma"}
            emb_retrieval = {"sentence-transformers", "bge", "e5", "openai embeddings", "cohere embeddings", "transformers", "huggingface", "embeddings"}
            nlp_ir = {"nlp", "natural language processing", "information retrieval", "search", "ranking", "re-ranking", "rag", "retrieval-augmented generation", "semantic search"}
            python_skill = {"python"}
            eval_frameworks = {"ndcg", "mrr", "map", "a/b testing", "ab testing", "evaluation", "evaluation frameworks"}
            
            skill_points = 0.0
            def get_skill_score(skill_set):
                max_score = 0.0
                for s_name, s_obj in skills_dict.items():
                    if any(target in s_name for target in skill_set):
                        prof = s_obj.get("proficiency", "beginner")
                        prof_mult = {"expert": 1.0, "advanced": 0.8, "intermediate": 0.6, "beginner": 0.3}.get(prof, 0.3)
                        dur = s_obj.get("duration_months", 0)
                        dur_mult = min(1.0, dur / 36.0)
                        
                        s_score = 6.0 * prof_mult * (0.5 + 0.5 * dur_mult)
                        if s_score > max_score:
                            max_score = s_score
                return max_score
                
            skill_points += get_skill_score(vec_dbs)
            skill_points += get_skill_score(emb_retrieval)
            skill_points += get_skill_score(nlp_ir)
            skill_points += get_skill_score(python_skill)
            skill_points += get_skill_score(eval_frameworks)
            score += skill_points
            
            # Nice-to-haves
            nice_to_haves = {"lora", "qlora", "peft", "xgboost", "lightgbm", "catboost", "learning to rank", "distributed systems", "vllm", "cuda"}
            nice_match_count = sum(1 for nth in nice_to_haves if any(nth in s_name for s_name in skills_dict))
            score += min(5.0, nice_match_count * 1.5)
            
            # 5. Location Alignment
            loc = profile.get("location", "").lower()
            country = profile.get("country", "").lower()
            willing_reloc = signals.get("willing_to_relocate", False)
            
            loc_score = 0.0
            if "pune" in loc or "noida" in loc:
                loc_score = 10.0
            elif country == "india" or "india" in loc:
                tier1_cities = ["bangalore", "bengaluru", "hyderabad", "mumbai", "chennai", "delhi", "gurgaon", "ncr", "kolkata"]
                if any(c in loc for c in tier1_cities):
                    loc_score = 8.0 if willing_reloc else 5.0
                else:
                    loc_score = 5.0 if willing_reloc else 2.0
            else:
                loc_score = 3.0 if willing_reloc else 0.0
            score += loc_score
            
            # --- BEHAVIORAL SIGNALS MULTIPLIERS ---
            multiplier = 1.0
            
            # Recruiter Response Rate
            rrr = signals.get("recruiter_response_rate", 1.0)
            if rrr < 0.1:
                multiplier *= 0.3
            elif rrr < 0.3:
                multiplier *= 0.6
            elif rrr < 0.5:
                multiplier *= 0.8
                
            # Last Active Date
            active_date = parse_date(signals.get("last_active_date"))
            if active_date:
                days_inactive = (today - active_date).days
                if days_inactive > 180:
                    multiplier *= 0.4
                elif days_inactive > 90:
                    multiplier *= 0.7
                elif days_inactive > 30:
                    multiplier *= 0.9
                    
            # Notice Period
            notice = signals.get("notice_period_days", 0)
            if notice <= 30:
                multiplier *= 1.0
            elif notice <= 60:
                multiplier *= 0.9
            elif notice <= 90:
                multiplier *= 0.8
            else:
                multiplier *= 0.6
                
            # Interview Completion Rate
            icr = signals.get("interview_completion_rate", 1.0)
            if icr < 0.4:
                multiplier *= 0.5
            elif icr < 0.7:
                multiplier *= 0.8
                
            # Open to work flag
            otw = signals.get("open_to_work_flag", True)
            if not otw:
                multiplier *= 0.85
                
            final_score = score * multiplier
            
            scored_candidates.append({
                "candidate_id": cid,
                "score": final_score,
                "candidate_data": candidate
            })
            
    # Sort candidates by rounded score descending, then candidate_id ascending for tiebreaks
    scored_candidates.sort(key=lambda x: (-round(x["score"], 4), x["candidate_id"]))
    
    # Take top 100
    top_100 = scored_candidates[:100]
    
    print(f"Writing top 100 ranked candidates to {args.out}...")
    
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        
        for i, sc in enumerate(top_100):
            rank = i + 1
            reasoning = generate_reasoning(sc["candidate_data"], rank)
            # Round score to 4 decimal places
            rounded_score = round(sc["score"], 4)
            writer.writerow([sc["candidate_id"], rank, rounded_score, reasoning])
            
    print("Ranking complete! Done.")

if __name__ == "__main__":
    main()
