
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = "student_portal_secret_key"

DB_NAME = "placement_portal.db"
UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# DATABASE CONNECTION
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# CREATE DATABASE TABLES
def init_db():
    with get_db() as db:

        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            course TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            skills TEXT DEFAULT '',
            resume TEXT DEFAULT '',
            approved INTEGER DEFAULT 0,
            role TEXT DEFAULT 'student'
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            eligibility TEXT DEFAULT '',
            posted_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Pending',
            applied_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, job_id),
            FOREIGN KEY(student_id) REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
                ON DELETE CASCADE
        );
        """)

        # CREATE ADMIN ACCOUNT
        admin = db.execute(
            "SELECT id FROM users WHERE email=?",
            ("admin@portal.com",)
        ).fetchone()

        if not admin:
            db.execute(
                """INSERT INTO users
                (name,email,password,approved,role)
                VALUES(?,?,?,?,?)""",
                (
                    "Portal Admin",
                    "admin@portal.com",
                    generate_password_hash("admin123"),
                    1,
                    "admin"
                )
            )

        # ADD SAMPLE JOBS
        count = db.execute(
            "SELECT COUNT(*) AS n FROM jobs"
        ).fetchone()["n"]

        if count == 0:
            jobs = [
                (
                    "Python Developer Intern",
                    "BrightByte Solutions",
                    "Pune",
                    "Work on Python applications.",
                    "Python basics"
                ),
                (
                    "Junior Web Developer",
                    "PixelCraft Technologies",
                    "Mumbai",
                    "Create responsive websites.",
                    "HTML, CSS, JavaScript"
                ),
                (
                    "Data Analyst Trainee",
                    "InsightWorks",
                    "Remote",
                    "Prepare reports and analyze data.",
                    "Python or Excel"
                )
            ]

            db.executemany(
                """INSERT INTO jobs
                (title,company,location,description,eligibility)
                VALUES(?,?,?,?,?)""",
                jobs
            )


# LOGIN CHECK
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


# ADMIN CHECK
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))

        return view(*args, **kwargs)

    return wrapped


# HOME PAGE
@app.route("/")
def home():

    with get_db() as db:
        job_count = db.execute(
            "SELECT COUNT(*) AS n FROM jobs"
        ).fetchone()["n"]

    return render_template(
        "index.html",
        job_count=job_count
    )


# STUDENT REGISTRATION
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        course = request.form.get("course", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not email or len(password) < 6:
            flash("Enter all details. Password must be 6 characters.", "danger")
            return render_template("register.html")

        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO users
                    (name,email,password,course,phone)
                    VALUES(?,?,?,?,?)""",
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        course,
                        phone
                    )
                )

            flash(
                "Registration successful. Wait for admin approval.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already registered.", "danger")

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email=?",
                (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):

            if user["role"] == "student" and not user["approved"]:
                flash("Waiting for admin approval.", "warning")
                return render_template("login.html")

            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()
    flash("Logged out successfully.", "success")

    return redirect(url_for("home"))


# STUDENT DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():

    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    with get_db() as db:

        student = db.execute(
            "SELECT * FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()

        jobs = db.execute("""
            SELECT j.*, a.id AS application_id, a.status
            FROM jobs j
            LEFT JOIN applications a
            ON j.id = a.job_id AND a.student_id=?
            ORDER BY j.posted_on DESC
        """, (session["user_id"],)).fetchall()

        applications = db.execute("""
            SELECT a.status, a.applied_on, j.title, j.company
            FROM applications a
            JOIN jobs j ON a.job_id=j.id
            WHERE a.student_id=?
            ORDER BY a.applied_on DESC
        """, (session["user_id"],)).fetchall()

    return render_template(
        "dashboard.html",
        student=student,
        jobs=jobs,
        applications=applications
    )


# STUDENT PROFILE
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    with get_db() as db:
        student = db.execute(
            "SELECT * FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        course = request.form.get("course", "").strip()
        phone = request.form.get("phone", "").strip()
        skills = request.form.get("skills", "").strip()

        resume_name = student["resume"]
        resume = request.files.get("resume")

        if resume and resume.filename:

            extension = resume.filename.rsplit(".", 1)[-1].lower()

            if extension not in ["pdf", "doc", "docx"]:
                flash("Upload PDF, DOC or DOCX only.", "danger")
                return render_template(
                    "profile.html",
                    student=student
                )

            resume_name = secure_filename(
                f"{session['user_id']}_{resume.filename}"
            )

            resume.save(
                os.path.join(UPLOAD_FOLDER, resume_name)
            )

        with get_db() as db:
            db.execute("""
                UPDATE users
                SET name=?, course=?, phone=?, skills=?, resume=?
                WHERE id=?
            """, (
                name,
                course,
                phone,
                skills,
                resume_name,
                session["user_id"]
            ))

        session["name"] = name

        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template(
        "profile.html",
        student=student
    )


# APPLY FOR JOB
@app.route("/apply/<int:job_id>", methods=["POST"])
@login_required
def apply(job_id):

    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    with get_db() as db:

        job = db.execute(
            "SELECT id FROM jobs WHERE id=?",
            (job_id,)
        ).fetchone()

        if not job:
            flash("Job not found.", "danger")

        else:
            try:
                db.execute(
                    """INSERT INTO applications
                    (student_id,job_id)
                    VALUES(?,?)""",
                    (session["user_id"], job_id)
                )

                flash("Application submitted successfully.", "success")

            except sqlite3.IntegrityError:
                flash("You already applied for this job.", "warning")

    return redirect(url_for("dashboard"))


# ADMIN DASHBOARD
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():

    with get_db() as db:

        pending = db.execute("""
            SELECT * FROM users
            WHERE role='student' AND approved=0
            ORDER BY id DESC
        """).fetchall()

        students = db.execute("""
            SELECT * FROM users
            WHERE role='student'
            ORDER BY id DESC
        """).fetchall()

        jobs = db.execute("""
            SELECT * FROM jobs
            ORDER BY posted_on DESC
        """).fetchall()

        applications = db.execute("""
            SELECT
                a.id,
                a.status,
                a.applied_on,
                u.name AS student_name,
                u.email,
                j.title,
                j.company
            FROM applications a
            JOIN users u ON a.student_id=u.id
            JOIN jobs j ON a.job_id=j.id
            ORDER BY a.applied_on DESC
        """).fetchall()

    return render_template(
        "admin.html",
        pending=pending,
        students=students,
        jobs=jobs,
        applications=applications
    )


# APPROVE STUDENT
@app.route("/admin/approve/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def approve_student(user_id):

    with get_db() as db:
        db.execute(
            """UPDATE users SET approved=1
            WHERE id=? AND role='student'""",
            (user_id,)
        )

    flash("Student approved successfully.", "success")

    return redirect(url_for("admin_dashboard"))


# ADD JOB
@app.route("/admin/job/add", methods=["POST"])
@login_required
@admin_required
def add_job():

    title = request.form.get("title", "").strip()
    company = request.form.get("company", "").strip()
    location = request.form.get("location", "").strip()
    description = request.form.get("description", "").strip()
    eligibility = request.form.get("eligibility", "").strip()

    if title and company and location and description:

        with get_db() as db:
            db.execute("""
                INSERT INTO jobs
                (title,company,location,description,eligibility)
                VALUES(?,?,?,?,?)
            """, (
                title,
                company,
                location,
                description,
                eligibility
            ))

        flash("Job added successfully.", "success")

    else:
        flash("Please fill all required fields.", "danger")

    return redirect(url_for("admin_dashboard"))


# DELETE JOB
@app.route("/admin/job/delete/<int:job_id>", methods=["POST"])
@login_required
@admin_required
def delete_job(job_id):

    with get_db() as db:
        db.execute(
            "DELETE FROM jobs WHERE id=?",
            (job_id,)
        )

    flash("Job deleted successfully.", "success")

    return redirect(url_for("admin_dashboard"))


# UPDATE APPLICATION STATUS
@app.route(
    "/admin/application/<int:application_id>/<status>",
    methods=["POST"]
)
@login_required
@admin_required
def update_application(application_id, status):

    if status not in ["Pending", "Selected", "Rejected"]:
        flash("Invalid status.", "danger")

    else:
        with get_db() as db:
            db.execute(
                "UPDATE applications SET status=? WHERE id=?",
                (status, application_id)
            )

        flash("Application status updated.", "success")

    return redirect(url_for("admin_dashboard"))


# RUN WEBSITE
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
