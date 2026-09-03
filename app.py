from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import generate_password_hash, check_password_hash

import sqlite3
import os
import re


app = Flask(__name__)

app.secret_key = "gig-cooperative-secret-key"

DATABASE = "database/gig_cooperative.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():
    os.makedirs("database", exist_ok=True)

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'worker',
            skills TEXT DEFAULT '',
            experience INTEGER DEFAULT 0,
            rating REAL DEFAULT 5.0,
            completed_jobs INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------------
    # GIGS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gigs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            skills TEXT NOT NULL,
            location TEXT NOT NULL,
            budget REAL NOT NULL,
            duration INTEGER NOT NULL,
            status TEXT DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # APPLICATIONS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gig_id INTEGER NOT NULL,
            worker_id INTEGER NOT NULL,
            proposal TEXT NOT NULL,
            proposed_price REAL NOT NULL,
            match_score REAL DEFAULT 0,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gig_id) REFERENCES gigs(id),
            FOREIGN KEY (worker_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # REVIEWS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gig_id INTEGER NOT NULL,
            worker_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            rating REAL NOT NULL,
            review TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gig_id) REFERENCES gigs(id),
            FOREIGN KEY (worker_id) REFERENCES users(id),
            FOREIGN KEY (client_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # COOPERATIVE PROPOSALS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            yes_votes INTEGER DEFAULT 0,
            no_votes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # VOTES
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote TEXT NOT NULL,
            UNIQUE(proposal_id, user_id),
            FOREIGN KEY (proposal_id) REFERENCES proposals(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()

    conn.close()


# ============================================================
# SMART SKILL MATCHING
# ============================================================

def clean_skills(skill_text):

    if not skill_text:
        return set()

    skill_text = skill_text.lower()

    skills = re.split(r"[,;/|]+", skill_text)

    return {
        skill.strip()
        for skill in skills
        if skill.strip()
    }


def calculate_skill_match(worker_skills, gig_skills):

    worker_set = clean_skills(worker_skills)

    gig_set = clean_skills(gig_skills)

    if not gig_set:

        return 0

    matched = worker_set.intersection(gig_set)

    score = (len(matched) / len(gig_set)) * 100

    return round(score, 2)


# ============================================================
# FAIR WAGE ESTIMATOR
# ============================================================

def estimate_fair_wage(category, duration, experience):

    category_rates = {
        "Technology": 1000,
        "Design": 800,
        "Writing": 600,
        "Marketing": 700,
        "Delivery": 400,
        "Cleaning": 350,
        "Repair": 600,
        "Education": 700,
        "Other": 500
    }

    base_rate = category_rates.get(category, 500)

    experience_bonus = experience * 100

    estimated = (
        base_rate * max(duration, 1)
    ) + experience_bonus

    return round(estimated, 2)


# ============================================================
# WORKER REPUTATION SCORE
# ============================================================

def calculate_reputation(user):

    rating = float(user["rating"])

    completed = int(user["completed_jobs"])

    experience = int(user["experience"])

    score = (
        rating * 10
        + min(completed * 2, 30)
        + min(experience * 3, 20)
    )

    return min(round(score, 2), 100)


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    conn = get_db()

    gigs = conn.execute("""
        SELECT gigs.*, users.name AS client_name
        FROM gigs
        JOIN users ON gigs.client_id = users.id
        WHERE gigs.status = 'Open'
        ORDER BY gigs.id DESC
        LIMIT 6
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        gigs=gigs
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = request.form["email"].strip().lower()

        password = request.form["password"]

        role = request.form["role"]

        skills = request.form.get("skills", "").strip()

        experience = request.form.get("experience", 0)

        try:
            experience = int(experience)
        except ValueError:
            experience = 0

        if not name or not email or not password:

            flash("Please fill all required fields.")

            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (name, email, password, role, skills, experience)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                hashed_password,
                role,
                skills,
                experience
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            flash("This email is already registered.")

            return redirect(url_for("register"))

        conn.close()

        flash("Registration successful.")

        return redirect(url_for("login"))

    return render_template("register.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            session["user_name"] = user["name"]

            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(url_for("login"))

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    reputation = calculate_reputation(user)

    # --------------------------------------------------------
    # CLIENT DATA
    # --------------------------------------------------------

    if user["role"] == "client":

        gigs = conn.execute("""
            SELECT *
            FROM gigs
            WHERE client_id = ?
            ORDER BY id DESC
        """, (
            session["user_id"],
        )).fetchall()

        conn.close()

        return render_template(
            "dashboard.html",
            user=user,
            gigs=gigs,
            reputation=reputation,
            applications=[]
        )

    # --------------------------------------------------------
    # WORKER DATA
    # --------------------------------------------------------

    applications = conn.execute("""
        SELECT
            applications.*,
            gigs.title AS gig_title,
            gigs.category AS gig_category,
            gigs.budget AS gig_budget
        FROM applications
        JOIN gigs
        ON applications.gig_id = gigs.id
        WHERE applications.worker_id = ?
        ORDER BY applications.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    gigs = conn.execute("""
        SELECT *
        FROM gigs
        WHERE status = 'Open'
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        gigs=gigs,
        applications=applications,
        reputation=reputation
    )


# ============================================================
# VIEW ALL GIGS
# ============================================================

@app.route("/gigs")
def gigs():

    search = request.args.get("search", "").strip()

    category = request.args.get("category", "").strip()

    conn = get_db()

    query = """
        SELECT gigs.*, users.name AS client_name
        FROM gigs
        JOIN users ON gigs.client_id = users.id
        WHERE gigs.status = 'Open'
    """

    params = []

    if search:

        query += """
            AND (
                gigs.title LIKE ?
                OR gigs.description LIKE ?
                OR gigs.skills LIKE ?
            )
        """

        search_value = f"%{search}%"

        params.extend([
            search_value,
            search_value,
            search_value
        ])

    if category:

        query += """
            AND gigs.category = ?
        """

        params.append(category)

    query += """
        ORDER BY gigs.id DESC
    """

    all_gigs = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    return render_template(
        "gigs.html",
        gigs=all_gigs,
        search=search,
        category=category
    )


# ============================================================
# POST A GIG
# ============================================================

@app.route("/post-gig", methods=["GET", "POST"])
def post_gig():

    if "user_id" not in session:

        return redirect(url_for("login"))

    if session["role"] != "client":

        flash("Only clients can post gigs.")

        return redirect(url_for("dashboard"))

    if request.method == "POST":

        title = request.form["title"].strip()

        description = request.form["description"].strip()

        category = request.form["category"]

        skills = request.form["skills"].strip()

        location = request.form["location"].strip()

        budget = request.form["budget"]

        duration = request.form["duration"]

        try:

            budget = float(budget)

            duration = int(duration)

        except ValueError:

            flash("Budget and duration must be valid numbers.")

            return redirect(url_for("post_gig"))

        conn = get_db()

        conn.execute("""
            INSERT INTO gigs
            (
                client_id,
                title,
                description,
                category,
                skills,
                location,
                budget,
                duration
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            description,
            category,
            skills,
            location,
            budget,
            duration
        ))

        conn.commit()

        conn.close()

        flash("Gig posted successfully.")

        return redirect(url_for("dashboard"))

    return render_template("post_gig.html")


# ============================================================
# GIG DETAILS
# ============================================================

@app.route("/gig/<int:gig_id>")
def gig_details(gig_id):

    conn = get_db()

    gig = conn.execute("""
        SELECT gigs.*, users.name AS client_name
        FROM gigs
        JOIN users ON gigs.client_id = users.id
        WHERE gigs.id = ?
    """, (
        gig_id,
    )).fetchone()

    applications = conn.execute("""
        SELECT
            applications.*,
            users.name AS worker_name,
            users.skills,
            users.rating,
            users.completed_jobs,
            users.experience
        FROM applications
        JOIN users
        ON applications.worker_id = users.id
        WHERE applications.gig_id = ?
    """, (
        gig_id,
    )).fetchall()

    conn.close()

    if not gig:

        flash("Gig not found.")

        return redirect(url_for("gigs"))

    fair_wage = estimate_fair_wage(
        gig["category"],
        gig["duration"],
        0
    )

    return render_template(
        "gig_details.html",
        gig=gig,
        applications=applications,
        fair_wage=fair_wage
    )


# ============================================================
# APPLY TO GIG
# ============================================================

@app.route("/gig/<int:gig_id>/apply", methods=["GET", "POST"])
def apply_gig(gig_id):

    if "user_id" not in session:

        return redirect(url_for("login"))

    if session["role"] != "worker":

        flash("Only workers can apply for gigs.")

        return redirect(url_for("gig_details", gig_id=gig_id))

    conn = get_db()

    gig = conn.execute("""
        SELECT *
        FROM gigs
        WHERE id = ?
    """, (
        gig_id,
    )).fetchone()

    worker = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    if not gig:

        conn.close()

        flash("Gig not found.")

        return redirect(url_for("gigs"))

    existing = conn.execute("""
        SELECT *
        FROM applications
        WHERE gig_id = ?
        AND worker_id = ?
    """, (
        gig_id,
        session["user_id"]
    )).fetchone()

    if existing:

        conn.close()

        flash("You have already applied for this gig.")

        return redirect(
            url_for("gig_details", gig_id=gig_id)
        )

    match_score = calculate_skill_match(
        worker["skills"],
        gig["skills"]
    )

    if request.method == "POST":

        proposal = request.form["proposal"].strip()

        proposed_price = request.form["proposed_price"]

        try:

            proposed_price = float(proposed_price)

        except ValueError:

            conn.close()

            flash("Enter a valid proposed price.")

            return redirect(
                url_for("apply_gig", gig_id=gig_id)
            )

        conn.execute("""
            INSERT INTO applications
            (
                gig_id,
                worker_id,
                proposal,
                proposed_price,
                match_score
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            gig_id,
            session["user_id"],
            proposal,
            proposed_price,
            match_score
        ))

        conn.commit()

        conn.close()

        flash(
            f"Application submitted. "
            f"Your skill match is {match_score}%."
        )

        return redirect(
            url_for("dashboard")
        )

    fair_wage = estimate_fair_wage(
        gig["category"],
        gig["duration"],
        worker["experience"]
    )

    conn.close()

    return render_template(
        "apply.html",
        gig=gig,
        worker=worker,
        match_score=match_score,
        fair_wage=fair_wage
    )


# ============================================================
# CLIENT ACCEPTS APPLICATION
# ============================================================

@app.route(
    "/application/<int:application_id>/accept",
    methods=["POST"]
)
def accept_application(application_id):

    if "user_id" not in session:

        return redirect(url_for("login"))

    conn = get_db()

    application = conn.execute("""
        SELECT
            applications.*,
            gigs.client_id,
            gigs.id AS gig_id
        FROM applications
        JOIN gigs
        ON applications.gig_id = gigs.id
        WHERE applications.id = ?
    """, (
        application_id,
    )).fetchone()

    if not application:

        conn.close()

        flash("Application not found.")

        return redirect(url_for("dashboard"))

    if application["client_id"] != session["user_id"]:

        conn.close()

        flash("You are not authorized.")

        return redirect(url_for("dashboard"))

    conn.execute("""
        UPDATE applications
        SET status = 'Accepted'
        WHERE id = ?
    """, (
        application_id,
    ))

    conn.execute("""
        UPDATE gigs
        SET status = 'In Progress'
        WHERE id = ?
    """, (
        application["gig_id"],
    ))

    conn.execute("""
        UPDATE applications
        SET status = 'Rejected'
        WHERE gig_id = ?
        AND id != ?
        AND status = 'Pending'
    """, (
        application["gig_id"],
        application_id
    ))

    conn.commit()

    conn.close()

    flash("Worker accepted successfully.")

    return redirect(url_for("dashboard"))


# ============================================================
# MARK GIG AS COMPLETED
# ============================================================

@app.route(
    "/gig/<int:gig_id>/complete",
    methods=["POST"]
)
def complete_gig(gig_id):

    if "user_id" not in session:

        return redirect(url_for("login"))

    conn = get_db()

    gig = conn.execute("""
        SELECT *
        FROM gigs
        WHERE id = ?
    """, (
        gig_id,
    )).fetchone()

    if not gig:

        conn.close()

        flash("Gig not found.")

        return redirect(url_for("dashboard"))

    if gig["client_id"] != session["user_id"]:

        conn.close()

        flash("Not authorized.")

        return redirect(url_for("dashboard"))

    application = conn.execute("""
        SELECT *
        FROM applications
        WHERE gig_id = ?
        AND status = 'Accepted'
        LIMIT 1
    """, (
        gig_id,
    )).fetchone()

    if not application:

        conn.close()

        flash("No accepted worker found.")

        return redirect(url_for("dashboard"))

    conn.execute("""
        UPDATE gigs
        SET status = 'Completed'
        WHERE id = ?
    """, (
        gig_id,
    ))

    conn.execute("""
        UPDATE applications
        SET status = 'Completed'
        WHERE id = ?
    """, (
        application["id"],
    ))

    conn.execute("""
        UPDATE users
        SET completed_jobs = completed_jobs + 1
        WHERE id = ?
    """, (
        application["worker_id"],
    ))

    conn.commit()

    conn.close()

    flash("Gig marked as completed.")

    return redirect(url_for("dashboard"))


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:

        return redirect(url_for("login"))

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    if request.method == "POST":

        name = request.form["name"].strip()

        skills = request.form.get(
            "skills",
            ""
        ).strip()

        experience = request.form.get(
            "experience",
            0
        )

        try:

            experience = int(experience)

        except ValueError:

            experience = 0

        conn.execute("""
            UPDATE users
            SET name = ?,
                skills = ?,
                experience = ?
            WHERE id = ?
        """, (
            name,
            skills,
            experience,
            session["user_id"]
        ))

        conn.commit()

        session["user_name"] = name

        flash("Profile updated successfully.")

    reputation = calculate_reputation(user)

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        reputation=reputation
    )


# ============================================================
# COOPERATIVE PAGE
# ============================================================

@app.route("/cooperative")
def cooperative():

    conn = get_db()

    proposals = conn.execute("""
        SELECT
            proposals.*,
            users.name AS creator_name
        FROM proposals
        JOIN users
        ON proposals.created_by = users.id
        ORDER BY proposals.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "cooperative.html",
        proposals=proposals
    )


# ============================================================
# CREATE PROPOSAL
# ============================================================

@app.route(
    "/cooperative/proposal",
    methods=["POST"]
)
def create_proposal():

    if "user_id" not in session:

        return redirect(url_for("login"))

    title = request.form["title"].strip()

    description = request.form["description"].strip()

    if not title or not description:

        flash("Please fill all proposal fields.")

        return redirect(url_for("cooperative"))

    conn = get_db()

    conn.execute("""
        INSERT INTO proposals
        (
            title,
            description,
            created_by
        )
        VALUES (?, ?, ?)
    """, (
        title,
        description,
        session["user_id"]
    ))

    conn.commit()

    conn.close()

    flash("Proposal created.")

    return redirect(url_for("cooperative"))


# ============================================================
# VOTE ON PROPOSAL
# ============================================================

@app.route(
    "/cooperative/vote/<int:proposal_id>/<vote>",
    methods=["POST"]
)
def vote_proposal(proposal_id, vote):

    if "user_id" not in session:

        return redirect(url_for("login"))

    if vote not in ["yes", "no"]:

        return redirect(url_for("cooperative"))

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM votes
        WHERE proposal_id = ?
        AND user_id = ?
    """, (
        proposal_id,
        session["user_id"]
    )).fetchone()

    if existing:

        flash("You have already voted on this proposal.")

        conn.close()

        return redirect(url_for("cooperative"))

    conn.execute("""
        INSERT INTO votes
        (
            proposal_id,
            user_id,
            vote
        )
        VALUES (?, ?, ?)
    """, (
        proposal_id,
        session["user_id"],
        vote
    ))

    if vote == "yes":

        conn.execute("""
            UPDATE proposals
            SET yes_votes = yes_votes + 1
            WHERE id = ?
        """, (
            proposal_id,
        ))

    else:

        conn.execute("""
            UPDATE proposals
            SET no_votes = no_votes + 1
            WHERE id = ?
        """, (
            proposal_id,
        ))

    conn.commit()

    conn.close()

    flash("Your vote has been recorded.")

    return redirect(url_for("cooperative"))


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
def admin():

    if "user_id" not in session:

        return redirect(url_for("login"))

    if session["role"] != "admin":

        flash("Admin access required.")

        return redirect(url_for("dashboard"))

    conn = get_db()

    total_users = conn.execute("""
        SELECT COUNT(*)
        FROM users
    """).fetchone()[0]

    total_workers = conn.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE role = 'worker'
    """).fetchone()[0]

    total_clients = conn.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE role = 'client'
    """).fetchone()[0]

    total_gigs = conn.execute("""
        SELECT COUNT(*)
        FROM gigs
    """).fetchone()[0]

    completed_gigs = conn.execute("""
        SELECT COUNT(*)
        FROM gigs
        WHERE status = 'Completed'
    """).fetchone()[0]

    open_gigs = conn.execute("""
        SELECT COUNT(*)
        FROM gigs
        WHERE status = 'Open'
    """).fetchone()[0]

    conn.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_workers=total_workers,
        total_clients=total_clients,
        total_gigs=total_gigs,
        completed_gigs=completed_gigs,
        open_gigs=open_gigs
    )


# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )