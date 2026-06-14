from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DB_NAME = "delivery_mate.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        dong TEXT NOT NULL,
        ho TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        is_approved INTEGER DEFAULT 0,
        manner_score REAL DEFAULT 36.5,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        store_name TEXT NOT NULL,
        menu_summary TEXT NOT NULL,
        target_amount INTEGER NOT NULL,
        pickup_place TEXT NOT NULL,
        pickup_time TEXT NOT NULL,
        memo TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS participations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        paid INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        order_id INTEGER,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(reporter_id) REFERENCES users(id),
        FOREIGN KEY(target_user_id) REFERENCES users(id),
        FOREIGN KEY(order_id) REFERENCES orders(id)
    )
    """)

    admin = cur.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()

    if not admin:
        cur.execute("""
        INSERT INTO users
        (username, password_hash, name, dong, ho, is_admin, is_approved, manner_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "admin",
            generate_password_hash("admin123"),
            "관리자",
            "관리",
            "000",
            1,
            1,
            40.0,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    conn.commit()
    conn.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("로그인이 필요합니다.")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def current_user():
    if "user_id" not in session:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()

    return user


@app.context_processor
def inject_user():
    return {"me": current_user()}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        name = request.form["name"].strip()
        dong = request.form["dong"].strip()
        ho = request.form["ho"].strip()

        if not username or not password or not name or not dong or not ho:
            flash("모든 항목을 입력하세요.")
            return redirect(url_for("register"))

        conn = get_db()

        try:
            conn.execute("""
            INSERT INTO users
            (username, password_hash, name, dong, ho, is_admin, is_approved, manner_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                generate_password_hash(password),
                name,
                dong,
                ho,
                0,
                0,
                36.5,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))

            conn.commit()
            flash("회원가입 완료. 관리자 승인 후 이용할 수 있습니다.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("이미 사용 중인 아이디입니다.")

        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("login"))

        if user["is_approved"] == -1:
            flash("이용 정지된 계정입니다. 관리자에게 문의하세요.")
            return redirect(url_for("login"))

        if user["is_approved"] == 0 and not user["is_admin"]:
            flash("관리자 승인 대기 중입니다.")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])

        flash("로그인되었습니다.")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    orders = conn.execute("""
    SELECT
        o.*,
        u.name AS writer_name,
        COALESCE(SUM(p.amount), 0) AS current_amount,
        COUNT(p.id) AS participant_count
    FROM orders o
    JOIN users u ON o.user_id = u.id
    LEFT JOIN participations p ON o.id = p.order_id
    GROUP BY o.id
    ORDER BY
        CASE WHEN o.status = 'open' THEN 0 ELSE 1 END,
        o.id DESC
    """).fetchall()

    conn.close()

    return render_template("dashboard.html", orders=orders)


@app.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_order():
    if request.method == "POST":
        store_name = request.form["store_name"].strip()
        menu_summary = request.form["menu_summary"].strip()
        target_amount = int(request.form["target_amount"])
        pickup_place = request.form["pickup_place"].strip()
        pickup_time = request.form["pickup_time"].strip()
        memo = request.form.get("memo", "").strip()

        conn = get_db()

        conn.execute("""
        INSERT INTO orders
        (user_id, store_name, menu_summary, target_amount, pickup_place, pickup_time, memo, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            store_name,
            menu_summary,
            target_amount,
            pickup_place,
            pickup_time,
            memo,
            "open",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        conn.commit()
        conn.close()

        flash("공동 주문 모집 글이 등록되었습니다.")
        return redirect(url_for("dashboard"))

    return render_template("new_order.html")


@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    conn = get_db()

    order = conn.execute("""
    SELECT
        o.*,
        u.name AS writer_name,
        u.dong,
        u.ho,
        u.manner_score,
        COALESCE(SUM(p.amount), 0) AS current_amount
    FROM orders o
    JOIN users u ON o.user_id = u.id
    LEFT JOIN participations p ON o.id = p.order_id
    WHERE o.id = ?
    GROUP BY o.id
    """, (order_id,)).fetchone()

    if not order:
        conn.close()
        abort(404)

    participants = conn.execute("""
    SELECT
        p.*,
        u.name,
        u.dong,
        u.ho,
        u.manner_score
    FROM participations p
    JOIN users u ON p.user_id = u.id
    WHERE p.order_id = ?
    ORDER BY p.id DESC
    """, (order_id,)).fetchall()

    comments = conn.execute("""
    SELECT
        c.*,
        u.name
    FROM comments c
    JOIN users u ON c.user_id = u.id
    WHERE c.order_id = ?
    ORDER BY c.id ASC
    """, (order_id,)).fetchall()

    conn.close()

    return render_template(
        "order_detail.html",
        order=order,
        participants=participants,
        comments=comments
    )


@app.route("/orders/<int:order_id>/join", methods=["POST"])
@login_required
def join_order(order_id):
    item_name = request.form["item_name"].strip()
    amount = int(request.form["amount"])

    conn = get_db()

    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if not order or order["status"] != "open":
        conn.close()
        flash("참여할 수 없는 모집입니다.")
        return redirect(url_for("dashboard"))

    conn.execute("""
    INSERT INTO participations
    (order_id, user_id, item_name, amount, paid, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        order_id,
        session["user_id"],
        item_name,
        amount,
        0,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.execute("""
    UPDATE users
    SET manner_score = manner_score + 0.1
    WHERE id = ?
    """, (session["user_id"],))

    conn.commit()
    conn.close()

    flash("공동 주문에 참여했습니다. 매너 온도가 0.1 상승했습니다.")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/comment", methods=["POST"])
@login_required
def add_comment(order_id):
    message = request.form["message"].strip()

    if not message:
        flash("댓글 내용을 입력하세요.")
        return redirect(url_for("order_detail", order_id=order_id))

    conn = get_db()

    conn.execute("""
    INSERT INTO comments
    (order_id, user_id, message, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        order_id,
        session["user_id"],
        message,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/close", methods=["POST"])
@login_required
def close_order(order_id):
    conn = get_db()

    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if not order:
        conn.close()
        abort(404)

    if order["user_id"] != session["user_id"] and not session.get("is_admin"):
        conn.close()
        abort(403)

    conn.execute(
        "UPDATE orders SET status = 'closed' WHERE id = ?",
        (order_id,)
    )

    conn.commit()
    conn.close()

    flash("모집이 마감되었습니다.")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/report/<int:target_user_id>", methods=["POST"])
@login_required
def report_user(order_id, target_user_id):
    reason = request.form["reason"].strip()

    if not reason:
        flash("신고 사유를 입력하세요.")
        return redirect(url_for("order_detail", order_id=order_id))

    conn = get_db()

    conn.execute("""
    INSERT INTO reports
    (reporter_id, target_user_id, order_id, reason, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        target_user_id,
        order_id,
        reason,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    flash("신고가 접수되었습니다.")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = get_db()

    users = conn.execute("""
    SELECT *
    FROM users
    ORDER BY is_admin DESC, is_approved ASC, id DESC
    """).fetchall()

    reports = conn.execute("""
    SELECT
        r.*,
        reporter.name AS reporter_name,
        target.name AS target_name
    FROM reports r
    JOIN users reporter ON r.reporter_id = reporter.id
    JOIN users target ON r.target_user_id = target.id
    ORDER BY r.id DESC
    """).fetchall()

    conn.close()

    return render_template("admin.html", users=users, reports=reports)


@app.route("/admin/users/<int:user_id>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_user_action(user_id, action):
    if user_id == session["user_id"]:
        flash("본인 계정은 변경할 수 없습니다.")
        return redirect(url_for("admin"))

    status_map = {
        "approve": 1,
        "reject": 0,
        "suspend": -1,
        "activate": 1
    }

    if action not in status_map:
        abort(400)

    conn = get_db()

    conn.execute(
        "UPDATE users SET is_approved = ? WHERE id = ?",
        (status_map[action], user_id)
    )

    conn.commit()
    conn.close()

    flash("사용자 상태가 변경되었습니다.")
    return redirect(url_for("admin"))

init_db()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)