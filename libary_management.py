from flask import Flask, request, redirect, url_for, render_template_string, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import send_from_directory, abort
import sqlite3
import os

# -------------------- SECTION 1: APP SETTINGS --------------------
app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "smart-library-development-key-change-before-deployment"
)
DB_PATH = Path(__file__).with_name("library.db")
UPLOAD_DIR = Path(__file__).with_name("uploads") / "pdfs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_PDF_EXTENSIONS = {".pdf"}
MAX_PDF_SIZE = 25 * 1024 * 1024  # 25 MB per PDF


# -------------------- SECTION 2: DATABASE ------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and add missing columns without deleting saved records."""
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

        # Add semester column to an older database if it does not exist.
        book_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()
        }
        if "semester" not in book_columns:
            conn.execute("""
                ALTER TABLE books
                ADD COLUMN semester TEXT NOT NULL DEFAULT 'Not assigned'
            """)
        # Add PDF metadata to old databases without deleting existing book records.
        if "pdf_filename" not in book_columns:
            conn.execute("ALTER TABLE books ADD COLUMN pdf_filename TEXT")

        # Add the default admin only if no admin named "admin" exists.
        admin = conn.execute(
            "SELECT id FROM admins WHERE username = ?", ("admin",)
        ).fetchone()
        if admin is None:
            conn.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                ("admin", generate_password_hash("ChangeMe@123")),
            )

        # Add demo books only when the books table is empty.
        book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        if book_count == 0:
            conn.executemany("""
                INSERT INTO books (title, author, category, status, semester)
                VALUES (?, ?, ?, ?, ?)
            """, [
                ("Python Programming", "Reema Thareja", "Programming", "Available", "Semester 1"),
                ("Let Us C", "Yashavant Kanetkar", "Programming", "Available", "Semester 1"),
                ("Data Structures", "Seymour Lipschutz", "Computer Science", "Available", "Semester 3"),
                ("Database Management System", "Raghu Ramakrishnan", "Database", "Available", "Semester 4"),
                ("Operating System", "Galvin", "Computer Science", "Available", "Semester 5"),
            ])

        conn.commit()
    finally:
        conn.close()


# -------------------- SECTION 3: LOGIN PROTECTION ----------------
def login_required(role=None):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in first.")
                if role == "admin":
                    return redirect(url_for("admin_login"))
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You are not allowed to access that page.")
                return redirect(url_for("home"))
            return view_function(*args, **kwargs)
        return wrapped
    return decorator


# -------------------- SECTION 4: WEBSITE DESIGN / CSS -------------
# The home-page design is styled to match the screenshot:
# dark library background, centered branding, two portal cards,
# bottom feature strip, and footer.
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Manrope:wght@500;600;700;800&display=swap');
:root{--navy:#071630;--blue:#0867f2;--purple:#5934df;--ink:#10265d;--muted:#52658c}
*{box-sizing:border-box}
body{margin:0;font-family:'DM Sans',Arial,sans-serif;color:var(--ink);min-height:100vh;background:#071630}
a{color:inherit}
main{max-width:1180px;margin:28px auto;padding:0 22px;min-height:55vh}
header{color:#fff;padding:18px max(5%,calc((100% - 1180px)/2));background:#0b1935}
header h1{margin:0 0 4px;font-family:Manrope,Arial,sans-serif;font-size:25px}
header p{margin:0;color:#c5d0e8;font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:18px;margin-top:14px;align-items:center}
nav a{color:#eaf0ff;text-decoration:none;font-size:14px;font-weight:600}
nav a:hover{color:#aebfff}
footer{text-align:center;color:#aabbdc;padding:25px 18px;font-size:13px}
.panel{background:#fff;padding:28px;border:1px solid #e8edf7;border-radius:22px;margin:20px auto;box-shadow:0 16px 45px #172b5310}
.form-panel{max-width:490px;padding:34px}
h1,h2,h3{font-family:Manrope,'DM Sans',Arial,sans-serif;letter-spacing:-.4px}
h2{font-size:27px;margin:0 0 10px}
label{display:block;font-weight:700;font-size:14px;margin:17px 0 8px}
input,select{width:100%;padding:13px 14px;border:1px solid #dce4f1;border-radius:11px;font-size:15px;background:#fbfcff;color:var(--ink);outline:none}
input:focus,select:focus{border-color:#6684ff;box-shadow:0 0 0 4px #315efb18;background:white}
button,.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:12px 17px;border:0;border-radius:11px;cursor:pointer;font-size:14px;font-weight:700;text-decoration:none;text-align:center}
button:hover,.btn:hover{filter:brightness(1.04)}
.primary{background:linear-gradient(135deg,#0867f2,#075ce8);color:white;box-shadow:0 7px 17px #315efb2b}
.secondary{background:#edf1fa;color:#2c3b5b}
.danger{background:#fff0f0;color:#a32838}
.notice{background:#edf3ff;border:1px solid #d7e4ff;color:#274582;padding:13px 16px;border-radius:12px}
.search{display:flex;gap:10px;margin:20px 0;align-items:center;flex-wrap:wrap}
.search input{flex:1;min-width:180px}
.search select{max-width:200px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}
.book{background:white;padding:22px;border:1px solid #e8edf7;border-radius:18px;box-shadow:0 8px 26px #172b5308;overflow-wrap:anywhere}
.book h3{margin:12px 0;font-size:18px}
.status{display:inline-block;padding:7px 11px;border-radius:30px;font-size:12px;font-weight:700}
.available{background:#e2f9ed;color:#147448}.issued{background:#fff0f0;color:#a32838}
.actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:15px}
.helper{color:var(--muted);font-size:13px}
.portal-home{max-width:1440px;margin:0 auto;padding:26px 5% 0;color:#fff;background:
linear-gradient(90deg,rgba(4,15,35,.20),rgba(4,15,35,.88) 27%,rgba(4,15,35,.90) 73%,rgba(4,15,35,.12)),
radial-gradient(ellipse at center,#18335d 0%,#091832 68%,#071329 100%);min-height:calc(100vh - 0px);position:relative;overflow:hidden}
.portal-home:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(5,18,42,.35) 18%,rgba(5,18,42,.20) 82%,transparent);pointer-events:none}
.brand{position:relative;text-align:center;padding-top:12px}
.brand-logo{font-size:70px;line-height:1;color:#55b6ff;display:inline-block;vertical-align:middle;margin-right:20px;text-shadow:0 0 22px #1388ff55}
.brand-title{display:inline-block;vertical-align:middle;text-align:left;font-size:clamp(32px,4.2vw,58px);font-weight:800;letter-spacing:-1.8px}
.brand-title span,.welcome span{color:#35a9ff}
.tagline{font-size:21px;color:#b7c9ed;margin-top:6px}
.welcome{text-align:center;position:relative;margin:42px 0 32px}
.welcome h2{font-size:clamp(27px,3vw,40px);margin:0 0 8px;color:#fff}
.welcome p{font-size:24px;color:#bed0f2;margin:0}
.portal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;max-width:980px;margin:0 auto;position:relative}
.portal-card{position:relative;overflow:hidden;display:flex;flex-direction:column;min-height:440px;background:linear-gradient(180deg,#cce7ff 0%,#fff 47%,#f4f8ff 100%);color:#10265d;border-radius:27px;padding:0 38px 34px;box-shadow:0 18px 40px #0003;transition:transform .2s}
.portal-card.admin{background:linear-gradient(180deg,#e8d9ff 0%,#fff 47%,#f7f4ff 100%)}
.portal-art{height:190px;margin:0 -38px 10px;display:flex;align-items:center;justify-content:center;position:relative;background:radial-gradient(ellipse at 45% 45%,#78bcff 0,#cce8ff 58%,transparent 59%)}
.admin .portal-art{background:radial-gradient(ellipse at 48% 45%,#c5a4ff 0,#ebddff 58%,transparent 59%)}
.person-art{font-size:90px;filter:drop-shadow(0 8px 5px #0002)}
.portal-icon{position:absolute;left:32px;bottom:-24px;width:94px;height:94px;display:grid;place-items:center;border-radius:50%;font-size:43px;color:#fff;background:linear-gradient(135deg,#0780ff,#0649c7);border:9px solid #f4f8ff;box-shadow:0 7px 22px #176dfb44}
.admin .portal-icon{background:linear-gradient(135deg,#7048f2,#4922be);box-shadow:0 7px 22px #7048f244}
.portal-card h3{font-size:30px;margin:30px 0 10px;color:#10265d}
.portal-card p{font-size:19px;line-height:1.45;color:#294477;margin:0 0 22px}
.portal-card .btn{margin-top:auto;width:100%;font-size:19px;padding:17px;border-radius:14px}
.admin .primary{background:linear-gradient(135deg,#4a36e7,#6533dc)}
.features{position:relative;max-width:1180px;margin:34px auto 0;border:1px solid #ffffff70;background:#182746b8;border-radius:20px;display:grid;grid-template-columns:repeat(4,1fr);padding:22px 16px}
.feature{display:flex;align-items:center;justify-content:center;gap:15px;padding:0 12px;border-right:1px solid #8293b8}
.feature:last-child{border-right:0}
.feature-icon{font-size:32px;color:#fff}
.feature strong{display:block;font-size:15px;color:#fff}
.feature small{display:block;font-size:12px;color:#cbd8f0;margin-top:5px}
.home-footer{position:relative;text-align:center;color:#c1cde3;padding:22px 10px 12px;font-size:13px}
@media(max-width:800px){.portal-home{padding:20px 16px}.portal-grid{grid-template-columns:1fr;max-width:520px}.portal-card{min-height:410px}.features{grid-template-columns:repeat(2,1fr);gap:18px}.feature:nth-child(2){border-right:0}.brand-logo{font-size:45px;margin-right:8px}.tagline{font-size:16px}.welcome{margin:30px 0}.welcome p{font-size:18px}}
@media(max-width:480px){.brand-title{font-size:29px}.portal-card{padding-left:24px;padding-right:24px}.portal-art{margin-left:-24px;margin-right:-24px}.features{grid-template-columns:1fr}.feature{border-right:0;border-bottom:1px solid #8293b8;padding:10px}.feature:last-child{border-bottom:0}.form-panel{padding:24px}}
</style>
"""


# -------------------- SECTION 5: SHARED PAGE LAYOUT ---------------
def page(content, **context):
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Libary Management</title>
      {{ style|safe }}
    </head>
    <body>
      {% if not is_portal_home %}
      <header>
        <h1>📚 Libary Management</h1>
        <p>Read • Learn • Grow</p>
        <nav>
          {% if session.get('user_id') %}
            <a href="{{ url_for('home') }}">Home / Books</a>
            {% if session.get('role') == 'admin' %}
              <a href="{{ url_for('add_book') }}">Add Book</a>
              <span>Admin: {{ session.get('username') }}</span>
            {% else %}
              <a href="{{ url_for('dashboard') }}">Student Dashboard</a>
              <span>Student: {{ session.get('name', 'Student') }}</span>
            {% endif %}
            <a href="{{ url_for('logout') }}">Logout</a>
          {% else %}
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('login') }}">Student Login</a>
            <a href="{{ url_for('register') }}">Register</a>
            <a href="{{ url_for('admin_login') }}">Admin Login</a>
          {% endif %}
        </nav>
      </header>
      {% endif %}
      <main {% if is_portal_home %}style="max-width:none;margin:0;padding:0;min-height:0"{% endif %}>
        {% with messages = get_flashed_messages() %}
          {% for message in messages %}<p class="notice">{{ message }}</p>{% endfor %}
        {% endwith %}
        """ + content + """
      </main>
      {% if not is_portal_home %}<footer>Libary Management</footer>{% endif %}
    </body>
    </html>
    """
    context.setdefault("is_portal_home", False)
    return render_template_string(template, style=STYLE, **context)


# -------------------- SECTION 6: HOME PAGE + BOOK FILTERS ----------
@app.route("/")
def home():
    # Visitors see the portal selection page. Logged-in users see the book catalogue.
    if not session.get("user_id"):
        content = """
        <div class="portal-home">
          <section class="brand">
            <div class="brand-logo">📖</div>
            <div class="brand-title">Libary <span>Management</span>
              <div class="tagline">Read&nbsp; • &nbsp;Learn&nbsp; • &nbsp;Grow</div>
            </div>
          </section>
          <section class="welcome">
            <h2>Welcome to Libary <span>Management</span></h2>
            <p>Choose your portal to continue</p>
          </section>
          <section class="portal-grid">
            <article class="portal-card">
              <div class="portal-art"><div class="person-art">👨🏻‍💻</div>
                <div class="portal-icon">🎓</div>
              </div>
              <h3>Student Portal</h3>
              <p>Search books, borrow/return, and<br> manage your library account.</p>
              <a class="btn primary" href="{{ url_for('login') }}">Student Login &nbsp; →</a>
            </article>
            <article class="portal-card admin">
              <div class="portal-art"><div class="person-art">👨🏻‍💼</div>
                <div class="portal-icon">🛡</div>
              </div>
              <h3>Admin Portal</h3>
              <p>Manage books, students, and<br> library records efficiently.</p>
              <a class="btn primary" href="{{ url_for('admin_login') }}">Admin Login &nbsp; →</a>
            </article>
          </section>
          <section class="features">
            <div class="feature"><div class="feature-icon">📖</div><div><strong>Huge Collection</strong><small>Thousands of books</small></div></div>
            <div class="feature"><div class="feature-icon">♧</div><div><strong>Easy Access</strong><small>For all students</small></div></div>
            <div class="feature"><div class="feature-icon">🛡</div><div><strong>Secure &amp; Reliable</strong><small>Your data is safe</small></div></div>
            <div class="feature"><div class="feature-icon">🌱</div><div><strong>Better Future</strong><small>Through Knowledge</small></div></div>
          </section>
          <div class="home-footer">© 2025 Libary Management. All rights reserved.</div>
        </div>
        """
        return page(content, is_portal_home=True)

    search = request.args.get("search", "").strip()
    semester = request.args.get("semester", "").strip()
    year = request.args.get("year", "").strip()
    valid_years = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
    year_semesters = {
        "1st Year": ["Semester 1", "Semester 2"],
        "2nd Year": ["Semester 3", "Semester 4"],
        "3rd Year": ["Semester 5", "Semester 6"],
        "4th Year": ["Semester 7", "Semester 8"],
    }
    if year not in valid_years:
        year = ""
    if semester not in [f"Semester {n}" for n in range(1, 9)]:
        semester = ""

    conditions, params = [], []
    if search:
        conditions.append("(title LIKE ? OR author LIKE ? OR category LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if semester:
        conditions.append("semester = ?")
        params.append(semester)
    elif year:
        conditions.append("semester IN (?, ?)")
        params.extend(year_semesters[year])

    sql = "SELECT * FROM books"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id DESC"

    conn = get_db()
    try:
        books = conn.execute(sql, params).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    finally:
        conn.close()

    content = """
    <section class="panel">
      <h2>Explore Books</h2><p>Total books: {{ total }}</p>
      <form class="search" method="GET" action="/">
        <input name="search" value="{{ search }}" placeholder="Search title, author or category">
        <select name="year"><option value="">All Years</option>
          {% for yr in ['1st Year','2nd Year','3rd Year','4th Year'] %}
          <option value="{{ yr }}" {% if year == yr %}selected{% endif %}>{{ yr }}</option>{% endfor %}
        </select>
        <select name="semester"><option value="">All Semesters</option>
          {% for sem in ['Semester 1','Semester 2','Semester 3','Semester 4','Semester 5','Semester 6','Semester 7','Semester 8'] %}
          <option value="{{ sem }}" {% if semester == sem %}selected{% endif %}>{{ sem }}</option>{% endfor %}
        </select>
        <button class="primary" type="submit">Search</button>
        <a class="btn secondary" href="{{ url_for('home') }}">Reset</a>
      </form>
      {% if session.get('role') == 'admin' %}<p><a class="btn primary" href="{{ url_for('add_book') }}">+ Add New Book</a></p>{% endif %}
      {% if books %}<div class="grid">
        {% for book in books %}
        <article class="book">
          <div style="font-size:30px">📖</div><h3>{{ book['title'] }}</h3>
          <p><b>Author:</b> {{ book['author'] }}</p><p><b>Category:</b> {{ book['category'] }}</p>
          <p><b>Semester:</b> {{ book['semester'] }}</p>
          {% if book['pdf_filename'] %}
          <div class="actions">
            <a class="btn primary" href="{{ url_for('read_pdf', book_id=book['id']) }}" target="_blank" rel="noopener">Read PDF</a>
            <a class="btn secondary" href="{{ url_for('download_pdf', book_id=book['id']) }}">Download PDF</a>
          </div>
          {% elif session.get('role') == 'admin' %}<p class="helper">PDF not uploaded yet. Edit this book to attach a PDF.</p>{% endif %}
          {% if book['status'] == 'Available' %}<span class="status available">Available</span>
          {% else %}<span class="status issued">Issued</span>{% endif %}
          {% if session.get('role') == 'admin' %}
          <div class="actions">
            <a class="btn secondary" href="{{ url_for('edit_book', book_id=book['id']) }}">Edit</a>
            <form method="POST" action="{{ url_for('delete_book', book_id=book['id']) }}" onsubmit="return confirm('Delete this book?');">
              <button class="danger" type="submit">Delete</button>
            </form>
          </div>{% endif %}
        </article>{% endfor %}
      </div>{% else %}<p>No books found. Try another search.</p>{% endif %}
    </section>
    """
    return page(content, books=books, total=total, search=search, semester=semester, year=year)


# -------------------- SECTION 7: STUDENT DASHBOARD ----------------
@app.route("/dashboard")
@login_required(role="student")
def dashboard():
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT student_id, name FROM students WHERE id = ?", (session["user_id"],)
        ).fetchone()
        total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        available_books = conn.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'Available'"
        ).fetchone()[0]
        recent_books = conn.execute(
            "SELECT * FROM books WHERE status = 'Available' ORDER BY id DESC LIMIT 6"
        ).fetchall()
    finally:
        conn.close()

    if student is None:
        session.clear()
        flash("Student account was not found. Please log in again.")
        return redirect(url_for("login"))

    content = """
    <section class="panel">
      <h2>Welcome, {{ student['name'] }}! 👋</h2>
      <p>Your Student ID: <b>{{ student['student_id'] }}</b></p>
      <p>Use this dashboard to find books for your semester.</p>
      <div class="grid">
        <div class="book"><p>Total Books</p><h2>{{ total_books }}</h2></div>
        <div class="book"><p>Currently Available</p><h2>{{ available_books }}</h2></div>
      </div>
      <h3>Find Books by Academic Year</h3><div class="actions">
        {% for yr in ['1st Year','2nd Year','3rd Year','4th Year'] %}
        <a class="btn secondary" href="{{ url_for('home', year=yr) }}">{{ yr }}</a>{% endfor %}
      </div>
      <h3>Find Books by Semester</h3><div class="actions">
        {% for sem in ['Semester 1','Semester 2','Semester 3','Semester 4','Semester 5','Semester 6','Semester 7','Semester 8'] %}
        <a class="btn secondary" href="{{ url_for('home', semester=sem) }}">{{ sem }}</a>{% endfor %}
        <a class="btn primary" href="{{ url_for('home') }}">Browse All Books</a>
      </div>
    </section>
    <section><h2>Recently Added Available Books</h2>
      {% if recent_books %}<div class="grid">{% for book in recent_books %}
      <article class="book"><div style="font-size:28px">📖</div><h3>{{ book['title'] }}</h3>
      <p><b>Author:</b> {{ book['author'] }}</p><p><b>Category:</b> {{ book['category'] }}</p>
      <p><b>Semester:</b> {{ book['semester'] }}</p><span class="status available">Available</span></article>
      {% endfor %}</div>{% else %}<p>No available books are listed yet.</p>{% endif %}
    </section>
    """
    return page(content, student=student, total_books=total_books,
                available_books=available_books, recent_books=recent_books)


# -------------------- SECTION 8: STUDENT REGISTRATION + LOGIN -----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if not student_id or not name or len(password) < 8:
            flash("Enter all details. Password must have at least 8 characters.")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO students (student_id, name, password_hash) VALUES (?, ?, ?)",
                (student_id, name, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("That Student ID is already registered.")
            return redirect(url_for("register"))
        finally:
            conn.close()

        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))

    content = """
    <div class="panel form-panel"><h2>Student Registration</h2>
      <form method="POST">
        <label for="student_id">Student ID</label><input id="student_id" name="student_id" required maxlength="50">
        <label for="name">Full Name</label><input id="name" name="name" required maxlength="100">
        <label for="password">Password (minimum 8 characters)</label>
        <input id="password" type="password" name="password" minlength="8" required autocomplete="new-password">
        <p><button class="primary" type="submit">Register</button></p>
      </form><p>Already registered? <a href="{{ url_for('login') }}">Student Login</a></p>
      <p><a href="{{ url_for('home') }}">← Back to home</a></p>
    </div>
    """
    return page(content)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        try:
            student = conn.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        finally:
            conn.close()

        if student and check_password_hash(student["password_hash"], password):
            session.clear()
            session["user_id"] = student["id"]
            session["role"] = "student"
            session["name"] = student["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid Student ID or password.")
        return redirect(url_for("login"))

    content = """
    <div class="panel form-panel"><h2>Student Login</h2>
      <form method="POST">
        <label for="student_id">Student ID</label><input id="student_id" name="student_id" required>
        <label for="password">Password</label><input id="password" type="password" name="password" required autocomplete="current-password">
        <p><button class="primary" style="width:100%" type="submit">Login to Student Portal →</button></p>
      </form><p>New student? <a href="{{ url_for('register') }}">Create an account</a></p>
      <p class="helper"><a href="{{ url_for('home') }}">← Back to portal selection</a></p>
    </div>
    """
    return page(content)


# -------------------- SECTION 9: ADMIN LOGIN -----------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        try:
            admin = conn.execute(
                "SELECT * FROM admins WHERE username = ?", (username,)
            ).fetchone()
        finally:
            conn.close()

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["user_id"] = admin["id"]
            session["role"] = "admin"
            session["username"] = admin["username"]
            return redirect(url_for("home"))

        flash("Invalid admin username or password. Default login works only if unchanged.")
        return redirect(url_for("admin_login"))

    content = """
    <div class="panel form-panel"><h2>Admin Login</h2>
      <form method="POST">
        <label for="username">Admin Username</label><input id="username" name="username" required autocomplete="username">
        <label for="password">Admin Password</label><input id="password" type="password" name="password" required autocomplete="current-password">
        <p><button class="primary" style="width:100%" type="submit">Login to Admin Portal →</button></p>
      </form><p class="helper">Use your administrator username and password.</p>
      <p class="helper"><a href="{{ url_for('home') }}">← Back to portal selection</a></p>
    </div>
    """
    return page(content)


# -------------------- SECTION 10: LOGOUT + BOOK MANAGEMENT --------
@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.")
    return redirect(url_for("home"))


@app.route("/add_book", methods=["GET", "POST"])
@login_required(role="admin")
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        semester = request.form.get("semester", "Not assigned").strip() or "Not assigned"
        status = request.form.get("status", "Available")
        pdf = request.files.get("pdf_file")
        pdf_filename = None
        if pdf and pdf.filename:
            safe_name = secure_filename(pdf.filename)
            if Path(safe_name).suffix.lower() not in ALLOWED_PDF_EXTENSIONS:
                flash("Only PDF files are allowed.")
                return redirect(url_for("add_book"))
            pdf.seek(0, os.SEEK_END)
            size = pdf.tell()
            pdf.seek(0)
            if size > MAX_PDF_SIZE:
                flash("PDF must be 25 MB or smaller.")
                return redirect(url_for("add_book"))
            pdf_filename = f"{os.urandom(8).hex()}_{safe_name}"
        if not title or not author or not category:
            flash("Please fill in all required fields.")
            return redirect(url_for("add_book"))
        if status not in ("Available", "Issued"):
            status = "Available"

        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO books (title, author, category, status, semester, pdf_filename)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, author, category, status, semester, pdf_filename))
            conn.commit()
            if pdf_filename:
                pdf.save(UPLOAD_DIR / pdf_filename)
        finally:
            conn.close()
        flash("Book added successfully!")
        return redirect(url_for("home"))

    content = """
    <div class="panel form-panel"><h2>Add New Book</h2>
      <form method="POST" enctype="multipart/form-data">
        <label>Book Name</label><input name="title" required maxlength="200">
        <label>Author</label><input name="author" required maxlength="150">
        <label>Category</label><input name="category" required maxlength="100">
        <label>Academic Year / Semester</label><select name="semester">
          <option>Not assigned</option>
          {% for sem in ['Semester 1','Semester 2','Semester 3','Semester 4','Semester 5','Semester 6','Semester 7','Semester 8'] %}
          <option>{{ sem }}</option>{% endfor %}
        </select>
        <label>Status</label><select name="status"><option>Available</option><option>Issued</option></select>
        <label>Book PDF (optional, maximum 25 MB)</label><input type="file" name="pdf_file" accept="application/pdf,.pdf">
        <p class="helper">PDF upload works on the current server. Before free hosting, configure persistent file storage.</p>
        <p><button class="primary" type="submit">Save Book</button></p>
      </form><p><a href="{{ url_for('home') }}">← Back to books</a></p>
    </div>
    """
    return page(content)


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
@login_required(role="admin")
def edit_book(book_id):
    conn = get_db()
    try:
        book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if book is None:
            flash("Book not found.")
            return redirect(url_for("home"))

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            author = request.form.get("author", "").strip()
            category = request.form.get("category", "").strip()
            semester = request.form.get("semester", "Not assigned").strip() or "Not assigned"
            status = request.form.get("status", "Available")
            pdf = request.files.get("pdf_file")
            new_pdf_filename = book["pdf_filename"] if "pdf_filename" in book.keys() else None
            if pdf and pdf.filename:
                safe_name = secure_filename(pdf.filename)
                if Path(safe_name).suffix.lower() not in ALLOWED_PDF_EXTENSIONS:
                    flash("Only PDF files are allowed.")
                    return redirect(url_for("edit_book", book_id=book_id))
                pdf.seek(0, os.SEEK_END)
                size = pdf.tell()
                pdf.seek(0)
                if size > MAX_PDF_SIZE:
                    flash("PDF must be 25 MB or smaller.")
                    return redirect(url_for("edit_book", book_id=book_id))
                new_pdf_filename = f"{os.urandom(8).hex()}_{safe_name}"
                pdf.save(UPLOAD_DIR / new_pdf_filename)
            if not title or not author or not category:
                flash("Please fill in all required fields.")
                return redirect(url_for("edit_book", book_id=book_id))
            if status not in ("Available", "Issued"):
                status = "Available"
            conn.execute("""
                UPDATE books SET title=?, author=?, category=?, status=?, semester=?, pdf_filename=?
                WHERE id=?
            """, (title, author, category, status, semester, new_pdf_filename, book_id))
            conn.commit()
            flash("Book updated successfully!")
            return redirect(url_for("home"))
    finally:
        conn.close()

    content = """
    <div class="panel form-panel"><h2>Edit Book</h2>
      <form method="POST" enctype="multipart/form-data">
        <label>Book Name</label><input name="title" value="{{ book['title'] }}" required maxlength="200">
        <label>Author</label><input name="author" value="{{ book['author'] }}" required maxlength="150">
        <label>Category</label><input name="category" value="{{ book['category'] }}" required maxlength="100">
        <label>Academic Year / Semester</label><select name="semester">
          {% for sem in ['Not assigned','Semester 1','Semester 2','Semester 3','Semester 4','Semester 5','Semester 6','Semester 7','Semester 8'] %}
          <option value="{{ sem }}" {% if book['semester'] == sem %}selected{% endif %}>{{ sem }}</option>{% endfor %}
        </select>
        <label>Replace / attach PDF (optional, maximum 25 MB)</label><input type="file" name="pdf_file" accept="application/pdf,.pdf">
        {% if book['pdf_filename'] %}<p class="helper">A PDF is currently attached. Choose a new PDF only if you want to replace it.</p>{% endif %}
        <label>Status</label><select name="status">
          <option value="Available" {% if book['status']=='Available' %}selected{% endif %}>Available</option>
          <option value="Issued" {% if book['status']=='Issued' %}selected{% endif %}>Issued</option>
        </select>
        <p><button class="primary" type="submit">Save Changes</button></p>
      </form><p><a href="{{ url_for('home') }}">← Back to books</a></p>
    </div>
    """
    return page(content, book=book)


@app.route("/delete_book/<int:book_id>", methods=["POST"])
@login_required(role="admin")
def delete_book(book_id):
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        flash("Book deleted successfully!" if cursor.rowcount else "Book not found.")
    finally:
        conn.close()
    return redirect(url_for("home"))


@app.route("/book/<int:book_id>/pdf")
@login_required()
def read_pdf(book_id):
    conn = get_db()
    try:
        book = conn.execute("SELECT pdf_filename FROM books WHERE id = ?", (book_id,)).fetchone()
    finally:
        conn.close()
    if not book or not book["pdf_filename"]:
        flash("No PDF is attached to this book yet.")
        return redirect(url_for("home"))
    filename = book["pdf_filename"]
    if not (UPLOAD_DIR / filename).is_file():
        flash("PDF file is missing from server storage. Please ask the admin to upload it again.")
        return redirect(url_for("home"))
    return send_from_directory(UPLOAD_DIR, filename, mimetype="application/pdf", as_attachment=False)


@app.route("/book/<int:book_id>/download")
@login_required()
def download_pdf(book_id):
    conn = get_db()
    try:
        book = conn.execute("SELECT pdf_filename FROM books WHERE id = ?", (book_id,)).fetchone()
    finally:
        conn.close()
    if not book or not book["pdf_filename"]:
        flash("No PDF is attached to this book yet.")
        return redirect(url_for("home"))
    filename = book["pdf_filename"]
    if not (UPLOAD_DIR / filename).is_file():
        flash("PDF file is missing from server storage. Please ask the admin to upload it again.")
        return redirect(url_for("home"))
    return send_from_directory(UPLOAD_DIR, filename, mimetype="application/pdf", as_attachment=True, download_name=filename)


# -------------------- SECTION 11: RUN APP --------------------------
# Database setup runs on startup. It does not delete existing rows.
init_db()

if __name__ == "__main__":
    app.run(debug=True)
