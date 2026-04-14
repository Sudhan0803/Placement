def parse_skills(skills_str):
    """Convert comma-separated skills string to set of lowercase trimmed skills"""
    if not skills_str:
        return set()
    return set([s.strip().lower() for s in skills_str.split(',') if s.strip()])

def compute_match_score(student, job):
    """
    Returns: (match_score, is_eligible, reason_details)
    match_score: 0-100 float
    is_eligible: bool (True if meets minimum GPA and at least one skill matches)
    reason_details: dict with 'gpa_pass', 'missing_skills', 'matched_skills', 'skill_percentage'
    """
    # Parse skills
    student_skills = parse_skills(student.skills)
    job_skills = parse_skills(job.required_skills)
    
    # Skill matching
    if not job_skills:
        matched_skills = set()
        skill_percentage = 100.0
    else:
        matched_skills = student_skills.intersection(job_skills)
        skill_percentage = (len(matched_skills) / len(job_skills)) * 100
    
    # GPA check
    gpa_pass = True
    if job.min_gpa and job.min_gpa > 0:
        gpa_pass = (student.gpa and student.gpa >= job.min_gpa)
    
    # Eligibility: GPA pass AND at least one skill match (if job has skills)
    is_eligible = gpa_pass and (skill_percentage > 0 if job_skills else True)
    
    # Compute overall score (weighted: 70% skills, 30% GPA)
    if gpa_pass and job.min_gpa and job.min_gpa > 0:
        gpa_score = min(100, (student.gpa / job.min_gpa) * 100) if job.min_gpa > 0 else 100
    else:
        gpa_score = 0 if not gpa_pass else 100
    
    # If GPA fails, overall score is low but still show skill percentage
    if not gpa_pass:
        match_score = skill_percentage * 0.5  # Half score due to GPA fail
    else:
        match_score = (skill_percentage * 0.7) + (gpa_score * 0.3)
    
    match_score = round(match_score, 2)
    
    missing_skills = job_skills - student_skills if job_skills else set()
    
    reason_details = {
        'gpa_pass': gpa_pass,
        'missing_skills': list(missing_skills),
        'matched_skills': list(matched_skills),
        'skill_percentage': round(skill_percentage, 2),
        'gpa_score': round(gpa_score, 2)
    }
    
    return match_score, is_eligible, reason_details

def get_rejection_reason(reason_details):
    """Generate human-readable rejection reason based on match details"""
    if not reason_details['gpa_pass']:
        return "Application rejected due to GPA below minimum requirement."
    elif reason_details['missing_skills']:
        missing = ', '.join(reason_details['missing_skills'][:5])
        return f"Application rejected due to missing required skills: {missing}."
    else:
        return "Application did not meet the required criteria."