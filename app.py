from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from config import Config
from models import db, User, StudentProfile, CompanyProfile, Job, Application, Interview
from matching import compute_match_score, get_rejection_reason, parse_skills
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------- Helper Functions -------------------
def get_student_profile(user):
    return StudentProfile.query.filter_by(user_id=user.id).first()

def get_company_profile(user):
    return CompanyProfile.query.filter_by(user_id=user.id).first()

def get_match_for_job(student, job):
    if not student.student_profile:
        return 0, False, {}
    return compute_match_score(student.student_profile, job)

# ------------------- Routes -------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        email = request.form['email']
        name = request.form['name']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        user = User(email=email, password_hash=password, role=role, name=name)
        db.session.add(user)
        db.session.commit()
        
        if role == 'student':
            profile = StudentProfile(user_id=user.id)
            db.session.add(profile)
        elif role == 'company':
            profile = CompanyProfile(user_id=user.id)
            db.session.add(profile)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')
            if user.role == 'student':
                return redirect(url_for('student_dashboard'))
            elif user.role == 'company':
                return redirect(url_for('company_dashboard'))
            else:
                return redirect(url_for('admin_dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

# ------------------- Student Routes -------------------
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        abort(403)
    profile = get_student_profile(current_user)
    applications = Application.query.filter_by(student_id=current_user.id).all()
    return render_template('student_dashboard.html', profile=profile, applications=applications)

@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
def student_profile():
    if current_user.role != 'student':
        abort(403)
    profile = get_student_profile(current_user)
    if request.method == 'POST':
        profile.roll_number = request.form['roll_number']
        profile.branch = request.form['branch']
        profile.graduation_year = int(request.form['graduation_year'])
        profile.gpa = float(request.form['gpa'])
        profile.skills = request.form['skills']
        profile.projects = request.form['projects']
        profile.resume_text = request.form['resume_text']
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student_dashboard'))
    return render_template('student_profile.html', profile=profile)

@app.route('/student/jobs')
@login_required
def student_jobs():
    if current_user.role != 'student':
        abort(403)
    jobs = Job.query.filter_by(is_active=True).all()
    student = current_user
    jobs_with_match = []
    for job in jobs:
        score, eligible, details = get_match_for_job(student, job)
        jobs_with_match.append({
            'job': job,
            'match_score': score,
            'eligible': eligible,
            'company': User.query.get(job.company_id)
        })
    jobs_with_match.sort(key=lambda x: x['match_score'], reverse=True)
    return render_template('student_jobs.html', jobs=jobs_with_match)

@app.route('/student/apply/<int:job_id>', methods=['GET', 'POST'])
@login_required
def apply_job(job_id):
    if current_user.role != 'student':
        abort(403)
    job = Job.query.get_or_404(job_id)
    student = current_user
    existing = Application.query.filter_by(student_id=current_user.id, job_id=job_id).first()
    if existing:
        flash('You have already applied for this job.', 'warning')
        return redirect(url_for('student_jobs'))
    
    match_score, eligible, details = get_match_for_job(student, job)
    
    if request.method == 'POST':
        app_obj = Application(
            student_id=current_user.id,
            job_id=job_id,
            match_score=match_score,
            status='pending'
        )
        db.session.add(app_obj)
        db.session.commit()
        flash('Application submitted successfully!', 'success')
        return redirect(url_for('student_applications'))
    
    return render_template('apply_job.html', job=job, match_score=match_score, eligible=eligible, details=details)

@app.route('/student/applications')
@login_required
def student_applications():
    if current_user.role != 'student':
        abort(403)
    applications = Application.query.filter_by(student_id=current_user.id).all()
    return render_template('student_applications.html', applications=applications)

# ------------------- Company Routes -------------------
@app.route('/company/dashboard')
@login_required
def company_dashboard():
    if current_user.role != 'company':
        abort(403)
    profile = get_company_profile(current_user)
    jobs = Job.query.filter_by(company_id=current_user.id).all()
    return render_template('company_dashboard.html', profile=profile, jobs=jobs)

@app.route('/company/profile', methods=['GET', 'POST'])
@login_required
def company_profile_edit():
    if current_user.role != 'company':
        abort(403)
    profile = get_company_profile(current_user)
    if request.method == 'POST':
        profile.company_name = request.form['company_name']
        profile.description = request.form['description']
        profile.industry = request.form['industry']
        profile.location = request.form['location']
        db.session.commit()
        flash('Company profile updated', 'success')
        return redirect(url_for('company_dashboard'))
    return render_template('company_profile_edit.html', profile=profile)

@app.route('/company/jobs')
@login_required
def company_jobs():
    if current_user.role != 'company':
        abort(403)
    jobs = Job.query.filter_by(company_id=current_user.id).all()
    return render_template('company_jobs.html', jobs=jobs)

@app.route('/company/job/new', methods=['GET', 'POST'])
@login_required
def new_job():
    if current_user.role != 'company':
        abort(403)
    if request.method == 'POST':
        job = Job(
            company_id=current_user.id,
            title=request.form['title'],
            description=request.form['description'],
            required_skills=request.form['required_skills'],
            min_gpa=float(request.form['min_gpa']) if request.form['min_gpa'] else 0.0,
            location=request.form['location'],
            is_active=True
        )
        db.session.add(job)
        db.session.commit()
        flash('Job posted successfully', 'success')
        return redirect(url_for('company_jobs'))
    return render_template('company_job_form.html', job=None)

@app.route('/company/job/edit/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    if current_user.role != 'company':
        abort(403)
    job = Job.query.get_or_404(job_id)
    if job.company_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        job.title = request.form['title']
        job.description = request.form['description']
        job.required_skills = request.form['required_skills']
        job.min_gpa = float(request.form['min_gpa']) if request.form['min_gpa'] else 0.0
        job.location = request.form['location']
        db.session.commit()
        flash('Job updated', 'success')
        return redirect(url_for('company_jobs'))
    return render_template('company_job_form.html', job=job)

@app.route('/company/job/<int:job_id>/applications')
@login_required
def company_applications(job_id):
    if current_user.role != 'company':
        abort(403)
    job = Job.query.get_or_404(job_id)
    if job.company_id != current_user.id:
        abort(403)
    applications = Application.query.filter_by(job_id=job_id).all()
    # Add match details for each application
    apps_data = []
    for app in applications:
        student = User.query.get(app.student_id)
        apps_data.append({
            'application': app,
            'student': student,
            'profile': student.student_profile
        })
    return render_template('company_applications.html', job=job, applications=apps_data)

@app.route('/company/application/<int:app_id>/review', methods=['POST'])
@login_required
def review_application(app_id):
    app = Application.query.get_or_404(app_id)
    job = Job.query.get(app.job_id)
    if job.company_id != current_user.id:
        abort(403)
    action = request.form['action']
    if action == 'shortlist':
        app.status = 'shortlisted'
        app.rejection_reason = None
        flash('Student shortlisted', 'success')
    elif action == 'reject':
        app.status = 'rejected'
        # Generate automatic reason based on match
        student = User.query.get(app.student_id)
        _, _, details = compute_match_score(student.student_profile, job)
        app.rejection_reason = get_rejection_reason(details)
        flash('Application rejected', 'warning')
    elif action == 'select':
        app.status = 'selected'
        flash('Student selected', 'success')
    db.session.commit()
    return redirect(url_for('company_applications', job_id=job.id))

@app.route('/company/recommendations/<int:job_id>')
@login_required
def company_recommendations(job_id):
    if current_user.role != 'company':
        abort(403)
    job = Job.query.get_or_404(job_id)
    if job.company_id != current_user.id:
        abort(403)
    # Get all students
    students = User.query.filter_by(role='student').all()
    recommendations = []
    for student in students:
        if student.student_profile:
            score, eligible, details = compute_match_score(student.student_profile, job)
            if eligible or score > 30:  # Show potentially good matches
                recommendations.append({
                    'student': student,
                    'profile': student.student_profile,
                    'score': score,
                    'eligible': eligible,
                    'missing_skills': details['missing_skills']
                })
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return render_template('company_recommendations.html', job=job, recommendations=recommendations)

# ------------------- Admin Routes -------------------
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        abort(403)
    total_students = User.query.filter_by(role='student').count()
    total_companies = User.query.filter_by(role='company').count()
    total_jobs = Job.query.count()
    total_applications = Application.query.count()
    return render_template('admin_dashboard.html', 
                          total_students=total_students,
                          total_companies=total_companies,
                          total_jobs=total_jobs,
                          total_applications=total_applications)

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        abort(403)
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/applications')
@login_required
def admin_applications():
    if current_user.role != 'admin':
        abort(403)
    applications = Application.query.all()
    apps_data = []
    for app in applications:
        student = User.query.get(app.student_id)
        job = Job.query.get(app.job_id)
        company = User.query.get(job.company_id) if job else None
        apps_data.append({
            'application': app,
            'student': student,
            'job': job,
            'company': company
        })
    return render_template('admin_applications.html', applications=apps_data)

@app.route('/admin/interview/schedule/<int:app_id>', methods=['GET', 'POST'])
@login_required
def schedule_interview(app_id):
    if current_user.role != 'admin':
        abort(403)
    app = Application.query.get_or_404(app_id)
    if request.method == 'POST':
        interview = Interview.query.filter_by(application_id=app_id).first()
        if not interview:
            interview = Interview(application_id=app_id)
        interview.scheduled_time = datetime.strptime(request.form['datetime'], '%Y-%m-%dT%H:%M')
        interview.meeting_link = request.form['meeting_link']
        interview.status = 'scheduled'
        db.session.add(interview)
        db.session.commit()
        flash('Interview scheduled successfully', 'success')
        return redirect(url_for('admin_applications'))
    return render_template('schedule_interview.html', application=app)

@app.route('/admin/user/delete/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin':
        abort(403)
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('Cannot delete admin', 'danger')
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.name} deleted', 'success')
    return redirect(url_for('admin_users'))

# ------------------- Run -------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin if none exists
        if not User.query.filter_by(role='admin').first():
            admin_pass = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(email='admin@placement.com', password_hash=admin_pass, role='admin', name='Admin')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)