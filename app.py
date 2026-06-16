import streamlit as st
import json
import pandas as pd
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Redrob Talent Ranker Sandbox",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling
st.markdown("""
    <style>
        .main {
            background-color: #f8f9fa;
        }
        .stButton>button {
            background-color: #6366f1;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 8px 16px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #4f46e5;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }
        .card {
            background-color: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            margin-bottom: 20px;
            border-top: 4px solid #6366f1;
        }
        .honeypot-card {
            background-color: #fff5f5;
            padding: 15px;
            border-radius: 8px;
            border-left: 5px solid #e53e3e;
            margin-bottom: 10px;
        }
        .metric-value {
            font-size: 24px;
            font-weight: 700;
            color: #6366f1;
        }
    </style>
""", unsafe_allow_html=True)

# Helper functions
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return None

def detect_honeypots_and_score(candidates, weights, run_modifiers=True):
    today = datetime(2026, 6, 16)
    services_companies = {
        "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
        "hcl", "tech mahindra", "l&t", "lnt", "mindtree", "mphasis"
    }
    
    scored_candidates = []
    honeypots = []
    
    for c in candidates:
        cid = c.get("candidate_id", "Unknown")
        profile = c.get("profile", {})
        skills = c.get("skills", [])
        history = c.get("career_history", [])
        education = c.get("education", [])
        signals = c.get("redrob_signals", {})
        
        # --- HONEYPOT FILTER ---
        is_honeypot = False
        reasons = []
        
        # 1. Zero duration expert skills
        expert_zero_dur = [s for s in skills if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0]
        if len(expert_zero_dur) >= 2:
            is_honeypot = True
            reasons.append(f"Expert in {len(expert_zero_dur)} skills with 0 months experience.")
            
        # 2. Date/duration inconsistencies
        oldest_start = None
        years_of_exp = profile.get("years_of_experience", 0)
        
        for i, job in enumerate(history):
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
                        reasons.append(f"Job at '{job.get('company')}' states duration of {dur_months} months, but date range permits only {delta_months} months.")
                    if end_str and end_dt < start_dt:
                        is_honeypot = True
                        reasons.append(f"Job at '{job.get('company')}' end_date is before start_date.")
                        
            dur_years = dur_months / 12.0
            if dur_years > years_of_exp + 0.1:
                is_honeypot = True
                reasons.append(f"Job at '{job.get('company')}' duration ({dur_years:.1f} years) exceeds total profile experience ({years_of_exp} years).")
        
        # 3. Career span vs total experience
        if oldest_start:
            career_span_years = ((today - oldest_start).days) / 365.25
            if years_of_exp > career_span_years + 1.0:
                is_honeypot = True
                reasons.append(f"Stated experience ({years_of_exp} years) exceeds actual career span ({career_span_years:.1f} years).")
                
        # 4. Education end_year before start_year
        for i, edu in enumerate(education):
            start_yr = edu.get("start_year")
            end_yr = edu.get("end_year")
            if start_yr and end_yr and end_yr < start_yr:
                is_honeypot = True
                reasons.append(f"Education degree at '{edu.get('institution')}' end year ({end_yr}) is before start year ({start_yr}).")
                
        if is_honeypot:
            honeypots.append({
                "candidate_id": cid,
                "name": profile.get("anonymized_name", "Anonymous"),
                "headline": profile.get("headline", ""),
                "reasons": reasons
            })
            continue
            
        # --- SCORING ENGINE ---
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
        score += exp_score * (weights.get("experience", 10.0) / 10.0)
        
        # 2. Company Profile
        companies_worked = [job.get("company", "").lower() for job in history]
        total_jobs = len(companies_worked)
        services_jobs_count = sum(1 for c in companies_worked if any(sc in c for sc in services_companies))
        
        company_score = 10.0
        if total_jobs > 0:
            if services_jobs_count == total_jobs:
                company_score = 0.0
            elif services_jobs_count > 0:
                company_score = 5.0
                
        avg_duration_months = sum(job.get("duration_months", 0) for job in history) / max(1, total_jobs)
        if avg_duration_months < 18.0 and total_jobs >= 3:
            company_score *= 0.6
        score += company_score * (weights.get("company", 10.0) / 10.0)
        
        # 3. Domain Title Fit
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
        score += title_match * (weights.get("domain", 15.0) / 15.0)
        
        # Unwanted roles penalty
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
        
        # 4. Technical Skills
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
        score += skill_points * (weights.get("skills", 30.0) / 30.0)
        
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
        score += loc_score * (weights.get("location", 10.0) / 10.0)
        
        # --- BEHAVIORAL MODIFIERS ---
        multiplier = 1.0
        if run_modifiers:
            rrr = signals.get("recruiter_response_rate", 1.0)
            if rrr < 0.1: multiplier *= 0.3
            elif rrr < 0.3: multiplier *= 0.6
            elif rrr < 0.5: multiplier *= 0.8
            
            active_date = parse_date(signals.get("last_active_date"))
            if active_date:
                days_inactive = (today - active_date).days
                if days_inactive > 180: multiplier *= 0.4
                elif days_inactive > 90: multiplier *= 0.7
                elif days_inactive > 30: multiplier *= 0.9
                
            notice = signals.get("notice_period_days", 0)
            if notice <= 30: multiplier *= 1.0
            elif notice <= 60: multiplier *= 0.9
            elif notice <= 90: multiplier *= 0.8
            else: multiplier *= 0.6
            
            icr = signals.get("interview_completion_rate", 1.0)
            if icr < 0.4: multiplier *= 0.5
            elif icr < 0.7: multiplier *= 0.8
            
            otw = signals.get("open_to_work_flag", True)
            if not otw: multiplier *= 0.85
            
        final_score = score * multiplier
        
        scored_candidates.append({
            "candidate_id": cid,
            "name": profile.get("anonymized_name", "Anonymous"),
            "title": profile.get("current_title", "Engineer"),
            "exp": years_of_exp,
            "location": profile.get("location", ""),
            "score": round(final_score, 4),
            "raw_score": round(score, 2),
            "multiplier": round(multiplier, 2),
            "data": c
        })
        
    scored_candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))
    return scored_candidates, honeypots

def generate_reasoning(candidate, rank):
    profile = candidate.get("profile", {})
    skills = candidate.get("skills", [])
    signals = candidate.get("redrob_signals", {})
    
    title = profile.get("current_title", "Engineer")
    exp = profile.get("years_of_experience", 0)
    loc = profile.get("location", "India")
    notice = signals.get("notice_period_days", 0)
    willing_reloc = signals.get("willing_to_relocate", False)
    
    vec_dbs = {"faiss", "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "chroma"}
    emb_retrieval = {"sentence-transformers", "bge", "e5", "openai embeddings", "cohere embeddings", "transformers", "huggingface", "embeddings"}
    nlp_ir = {"nlp", "natural language processing", "information retrieval", "search", "ranking", "re-ranking", "rag", "retrieval-augmented generation", "semantic search"}
    
    matched_skills = []
    for s in skills:
        s_name = s.get("name", "").lower()
        if any(db in s_name for db in vec_dbs) or any(emb in s_name for emb in emb_retrieval) or any(nlp in s_name for nlp in nlp_ir):
            matched_skills.append(s.get("name"))
            
    matched_skills_str = ", ".join(matched_skills[:3]) if matched_skills else "search architectures"
    cid_hash = hash(candidate.get("candidate_id", ""))
    
    verb = ["demonstrating strong expertise in", "with solid hands-on experience in", "exhibiting proven capability in", "with a clear background in"][cid_hash % 4]
    role_desc = [f"working as a {title}", f"shipped relevant systems as a {title}", f"currently positioned as a {title}"][cid_hash % 3]
    
    if rank <= 10:
        lead = f"Outstanding match for founding team with {exp:.1f} years of experience in ML/AI."
        body = f"Brings high-quality production experience, {verb} {matched_skills_str} while {role_desc}."
    elif rank <= 50:
        lead = f"Strong candidate with {exp:.1f} years of experience in NLP/IR systems."
        body = f"Shows solid background, {verb} {matched_skills_str} while {role_desc}."
    else:
        lead = f"Good technical alignment with {exp:.1f} years of experience."
        body = f"Matches backend and IR requirements, {verb} {matched_skills_str} while {role_desc}."
        
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

# --- APP UI ---
st.title("🎯 Redrob AI Talent Ranker Sandbox")
st.markdown("An interactive simulator and scoring engine to audit, rank, and discovery candidate matches for the Senior AI Engineer role.")

# Sidebar Configuration
st.sidebar.header("📁 Load Candidate Pool")
upload_option = st.sidebar.radio("Data Source", ["Use Sample Pool (50 Candidates)", "Upload Custom JSONL File"])

candidates_pool = []
if upload_option == "Use Sample Pool (50 Candidates)":
    try:
        with open("dataset/sample_candidates.json", "r", encoding="utf-8") as f:
            candidates_pool = json.load(f)
        st.sidebar.success(f"Loaded {len(candidates_pool)} sample candidates.")
    except Exception as e:
        st.sidebar.error(f"Error loading sample_candidates.json: {str(e)}")
else:
    uploaded_file = st.sidebar.file_uploader("Upload JSONL candidate file", type=["jsonl", "json"])
    if uploaded_file:
        try:
            content = uploaded_file.read().decode("utf-8")
            if uploaded_file.name.endswith(".jsonl"):
                candidates_pool = [json.loads(line) for line in content.splitlines() if line.strip()]
            else:
                candidates_pool = json.loads(content)
            st.sidebar.success(f"Successfully loaded {len(candidates_pool)} candidates.")
        except Exception as e:
            st.sidebar.error(f"Failed to parse file: {str(e)}")

# Sidebar weights
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Score Weighting Configuration")
w_exp = st.sidebar.slider("Experience Years Weight (Max 10)", 0.0, 15.0, 10.0)
w_comp = st.sidebar.slider("Company Profile & Stability (Max 10)", 0.0, 15.0, 10.0)
w_dom = st.sidebar.slider("Domain & Title Alignment (Max 15)", 0.0, 20.0, 15.0)
w_skills = st.sidebar.slider("Technical Skills Focus (Max 30)", 0.0, 40.0, 30.0)
w_loc = st.sidebar.slider("Location & Relocation (Max 10)", 0.0, 15.0, 10.0)

weights_dict = {
    "experience": w_exp,
    "company": w_comp,
    "domain": w_dom,
    "skills": w_skills,
    "location": w_loc
}

run_behavioral = st.sidebar.checkbox("Apply Behavioral Modifiers", value=True)

if candidates_pool:
    # Run the filtering and scoring
    scored, honeypots = detect_honeypots_and_score(candidates_pool, weights_dict, run_behavioral)
    
    # Overview Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
            <div class="card">
                <div style="color: #6b7280; font-size: 14px; font-weight: 600;">Total Analyzed</div>
                <div class="metric-value">{len(candidates_pool)} Candidates</div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div class="card" style="border-top-color: #e53e3e;">
                <div style="color: #6b7280; font-size: 14px; font-weight: 600;">Honeypots Discovered</div>
                <div class="metric-value" style="color: #e53e3e;">{len(honeypots)} Trap Profiles</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
            <div class="card" style="border-top-color: #10b981;">
                <div style="color: #6b7280; font-size: 14px; font-weight: 600;">Shortlisted Candidates</div>
                <div class="metric-value" style="color: #10b981;">{min(len(scored), 100)} Candidates</div>
            </div>
        """, unsafe_allow_html=True)
        
    # Main Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Candidate Shortlist", "🔍 Profile Inspector", "⚠️ Honeypot Audit"])
    
    with tab1:
        st.header("Top Ranked Candidates")
        st.markdown("The candidates below are ranked according to your custom weights and behavioral modifiers. Ties are broken alphabetically by Candidate ID.")
        
        # Prepare Dataframe
        df_list = []
        for rank_idx, c in enumerate(scored[:100]):
            rank = rank_idx + 1
            reasoning_str = generate_reasoning(c["data"], rank)
            df_list.append({
                "Rank": rank,
                "Candidate ID": c["candidate_id"],
                "Name": c["name"],
                "Current Title": c["title"],
                "Years Exp": c["exp"],
                "Location": c["location"],
                "Match Score": c["score"],
                "Base Score": c["raw_score"],
                "Modifier": c["multiplier"],
                "Reasoning": reasoning_str
            })
            
        if df_list:
            df = pd.DataFrame(df_list)
            st.dataframe(
                df,
                column_config={
                    "Match Score": st.column_config.NumberColumn(format="%.4f"),
                    "Modifier": st.column_config.NumberColumn(format="%.2f"),
                    "Reasoning": st.column_config.TextColumn(width="large")
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Export CSV
            csv_data = df[["Candidate ID", "Rank", "Match Score", "Reasoning"]].rename(columns={
                "Candidate ID": "candidate_id",
                "Rank": "rank",
                "Match Score": "score",
                "Reasoning": "reasoning"
            }).to_csv(index=False)
            
            st.download_button(
                label="📥 Download Ranked Shortlist CSV",
                data=csv_data,
                file_name="team_minipolling_sandbox.csv",
                mime="text/csv"
            )
        else:
            st.warning("No candidates matched the current criteria.")
            
    with tab2:
        st.header("Profile Inspector")
        if scored:
            selected_id = st.selectbox("Select Candidate to Inspect", [c["candidate_id"] for c in scored])
            selected_cand = next(c for c in scored if c["candidate_id"] == selected_id)
            c_data = selected_cand["data"]
            prof = c_data.get("profile", {})
            sig = c_data.get("redrob_signals", {})
            
            c_left, c_right = st.columns([1, 2])
            
            with c_left:
                st.subheader("General Info")
                st.write(f"**Name:** {prof.get('anonymized_name')}")
                st.write(f"**Current Title:** {prof.get('current_title')}")
                st.write(f"**Location:** {prof.get('location')}, {prof.get('country')}")
                st.write(f"**Total Exp:** {prof.get('years_of_experience')} Years")
                st.write(f"**Company size:** {prof.get('current_company_size')} | Industry: {prof.get('current_industry')}")
                
                st.subheader("Availability Modifiers")
                st.write(f"🟢 **Open to Work:** {sig.get('open_to_work_flag')}")
                st.write(f"📅 **Notice Period:** {sig.get('notice_period_days')} Days")
                st.write(f"💬 **Recruiter Response Rate:** {sig.get('recruiter_response_rate') * 100:.1f}%")
                st.write(f"⏰ **Avg Response Time:** {sig.get('avg_response_time_hours')} Hours")
                st.write(f"🎯 **Interview Completion Rate:** {sig.get('interview_completion_rate') * 100:.1f}%")
                st.write(f"🗓️ **Last Active:** {sig.get('last_active_date')}")
                
            with c_right:
                st.subheader("Summary")
                st.info(prof.get("summary"))
                
                st.subheader("Career History")
                for job in c_data.get("career_history", []):
                    with st.expander(f"💼 {job.get('title')} at {job.get('company')} ({job.get('duration_months')} Months)"):
                        st.write(f"**Dates:** {job.get('start_date')} to {job.get('end_date') or 'Present'}")
                        st.write(f"**Company Size:** {job.get('company_size')} | Industry: {job.get('industry')}")
                        st.write(job.get("description"))
                        
                st.subheader("Skills & Proficiency")
                skills_df_list = []
                for s in c_data.get("skills", []):
                    skills_df_list.append({
                        "Skill": s.get("name"),
                        "Proficiency": s.get("proficiency"),
                        "Months Experience": s.get("duration_months"),
                        "Endorsements": s.get("endorsements")
                    })
                if skills_df_list:
                    st.table(pd.DataFrame(skills_df_list))
        else:
            st.warning("No candidates available to inspect.")
            
    with tab3:
        st.header("Honeypot Audit Log")
        st.markdown("The following profiles were intercepted and discarded because they represent anomalous, synthetically generated honeypots:")
        
        if honeypots:
            for hp in honeypots:
                with st.container():
                    st.markdown(f"""
                        <div class="honeypot-card">
                            <span style="font-weight: 700; font-size: 15px; color: #c53030;">❌ {hp['candidate_id']} - {hp['name']}</span><br/>
                            <span style="font-size: 13px; color: #4a5568;"><b>Headline:</b> {hp['headline']}</span>
                            <ul style="margin-top: 5px; margin-bottom: 5px; padding-left: 20px; font-size: 13px; color: #742a2a;">
                                {"".join(f"<li>{r}</li>" for r in hp['reasons'])}
                            </ul>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.success("No honeypot profiles found in the candidate pool.")
else:
    st.info("Please select or upload a candidate pool in the sidebar to begin ranking.")
