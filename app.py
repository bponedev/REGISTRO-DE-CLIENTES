# app.py
from flask import (
    Flask, render_template, request, redirect, url_for, send_file, flash,
    session, abort
)
import sqlite3
import os
import io
import csv
import re
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# -------------------------
# Config
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET", "troque_para_uma_chave_secreta")  # troque em produção

# -------------------------
# DB helpers
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    # return rows as tuples (older templates expect numeric indexes)
    conn.row_factory = None
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            full_name TEXT,
            password_hash TEXT,
            role TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    # user_offices: many-to-many mapping
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_offices (
            user_id INTEGER,
            office_key TEXT,
            PRIMARY KEY (user_id, office_key)
        )
    """)

    # offices metadata
    c.execute("""
        CREATE TABLE IF NOT EXISTS offices_meta (
            office_key TEXT PRIMARY KEY,
            display_name TEXT
        )
    """)

    # excluidos (deleted)
    c.execute("""
        CREATE TABLE IF NOT EXISTS excluidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cpf TEXT,
            escritorio_nome TEXT,
            escritorio_chave TEXT,
            tipo_acao TEXT,
            data_fechamento TEXT,
            pendencias TEXT,
            numero_processo TEXT,
            data_protocolo TEXT,
            observacoes TEXT,
            captador TEXT,
            created_at TEXT,
            data_exclusao TEXT
        )
    """)

    conn.commit()
    conn.close()

    # create default admin if none exists
    ensure_default_admin()

def ensure_default_admin():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    if count == 0:
        # create default admin: username=admin password=admin
        pw_hash = generate_password_hash("admin")
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users (username, full_name, password_hash, role, active, created_at) VALUES (?,?,?,?,?,?)",
                  ("admin", "Administrador Padrão", pw_hash, "ADMIN", 1, now))
        # ensure central office exists
        register_office_meta("CENTRAL", "CENTRAL")
        # give admin access to all offices by design — we will allow ADMIN to bypass checks
        conn.commit()
    conn.close()

# -------------------------
# Office helpers (same structure used before)
# -------------------------
def normalize_office_raw(name: str) -> str:
    if not name:
        return ""
    s = name.strip()
    s = s.replace(" ", "_")
    s = re.sub(r'[^A-Za-z0-9_]', '', s)
    return s.upper()

def register_office_meta(office_key: str, display_name: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO offices_meta (office_key, display_name) VALUES (?,?)", (office_key, display_name))
        conn.commit()
    finally:
        conn.close()

def list_offices_meta():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT office_key, display_name FROM offices_meta ORDER BY display_name")
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({"key": r[0], "display": r[1]})
    # ensure CENTRAL exists
    if not any(o["key"] == "CENTRAL" for o in out):
        out.insert(0, {"key": "CENTRAL", "display": "CENTRAL"})
        register_office_meta("CENTRAL", "CENTRAL")
    return out

def get_office_display(office_key: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT display_name FROM offices_meta WHERE office_key=?", (office_key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return office_key.replace("_", " ").upper()

def create_office_table(office_key: str):
    if not office_key:
        office_key = "CENTRAL"
    table = f"office_{office_key}"
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cpf TEXT,
            escritorio_nome TEXT,
            escritorio_chave TEXT,
            tipo_acao TEXT,
            data_fechamento TEXT,
            pendencias TEXT,
            numero_processo TEXT,
            data_protocolo TEXT,
            observacoes TEXT,
            captador TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return table

def ensure_table_columns(table_name: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"PRAGMA table_info({table_name})")
        cols = [row[1] for row in c.fetchall()]
        needed = {
            "escritorio_nome": "TEXT",
            "escritorio_chave": "TEXT",
            "captador": "TEXT",
            "created_at": "TEXT"
        }
        for col, typ in needed.items():
            if col not in cols:
                c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {typ}")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

# -------------------------
# User helpers (auth & perms)
# -------------------------
def get_user_by_id(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, active FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "full_name": row[2], "role": row[3], "active": row[4]}

def get_user_by_username(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, password_hash, role, active FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "full_name": row[2], "password_hash": row[3], "role": row[4], "active": row[5]}

def get_user_offices(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT office_key FROM user_offices WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def user_has_office(user_id, office_key):
    if not office_key:
        return False
    if not get_user_by_id(user_id):
        return False
    # Admin has implicit access to all offices
    user = get_user_by_id(user_id)
    if user and user["role"] == "ADMIN":
        return True
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM user_offices WHERE user_id=? AND office_key=?", (user_id, office_key))
    r = c.fetchone()
    conn.close()
    return bool(r)

# -------------------------
# Auth decorators
# -------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        user = get_user_by_id(session["user_id"])
        if not user or user["active"] != 1:
            session.pop("user_id", None)
            flash("Sessão inválida. Faça login novamente.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def require_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            user = get_user_by_id(session["user_id"])
            if not user:
                session.pop("user_id", None)
                return redirect(url_for("login"))
            if user["role"] not in roles and user["role"] != "ADMIN":
                flash("Permissão negada.", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return wrapper

def office_edit_allowed(f):
    """
    Decorator to ensure that the current user can edit/mutate data of the target office.
    - Admin bypass
    - Supervisor bypass (optionally can be restricted; here Supervisor can edit any)
    - Operator must be linked to that office.
    The route must pass 'office' parameter via GET/POST or kwargs.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = get_user_by_id(session["user_id"])
        if not user:
            session.pop("user_id", None)
            return redirect(url_for("login"))
        # Admin always allowed
        if user["role"] == "ADMIN":
            return f(*args, **kwargs)
        # Supervisor allowed to edit offices they are assigned to (or all if you prefer)
        # We'll allow SUPERVISOR to act like OPERATOR but also allow viewing excluidos (checked elsewhere)
        office_param = request.values.get("office") or request.args.get("office") or kwargs.get("office") or request.form.get("office") or None
        # If target office not provided, allow (some routes use id only)
        if not office_param:
            return f(*args, **kwargs)
        office_key = normalize_office_raw(office_param)
        if user["role"] in ("SUPERVISOR",):
            # Supervisor allowed if assigned
            if user_has_office(user["id"], office_key):
                return f(*args, **kwargs)
            flash("Supervisor não vinculado a este escritório.", "error")
            return redirect(url_for("index"))
        if user["role"] == "OPERADOR":
            if user_has_office(user["id"], office_key):
                return f(*args, **kwargs)
            flash("Operador não autorizado para este escritório.", "error")
            return redirect(url_for("index"))
        # Visualizador cannot edit
        flash("Usuário sem permissão de edição.", "error")
        return redirect(url_for("index"))
    return decorated

# -------------------------
# Initialize DB & default admin
# -------------------------
init_db()

# -------------------------
# Auth routes
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = get_user_by_username(username)
        if not u or not u["active"]:
            flash("Usuário inválido ou inativo.", "error")
            return render_template("login.html")
        if check_password_hash(u["password_hash"], password):
            session["user_id"] = u["id"]
            flash("Login efetuado.", "success")
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
        else:
            flash("Usuário ou senha incorretos.", "error")
            return render_template("login.html")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Desconectado.", "info")
    return redirect(url_for("login"))

# helper current_user for templates
@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        user = get_user_by_id(session["user_id"])
    return {"current_user": user}

# -------------------------
# Admin - Users management
# -------------------------
@app.route("/admin/users")
@require_roles("ADMIN")
def admin_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, role, active, created_at FROM users ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    # annotate offices
    users = []
    for r in rows:
        uid = r[0]
        u_offs = get_user_offices(uid)
        users.append({
            "id": uid, "username": r[1], "full_name": r[2], "role": r[3], "active": r[4], "created_at": r[5],
            "offices": u_offs
        })
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/create", methods=["GET", "POST"])
@require_roles("ADMIN")
def admin_users_create():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "OPERADOR")
        offices = request.form.getlist("offices")  # office keys
        if not username or not password:
            flash("Username e senha são obrigatórios.", "error")
            return redirect(url_for("admin_users_create"))
        pw_hash = generate_password_hash(password)
        now = datetime.utcnow().isoformat()
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, full_name, password_hash, role, active, created_at) VALUES (?,?,?,?,?,?)",
                      (username, full_name, pw_hash, role, 1, now))
            uid = c.lastrowid
            for ok in offices:
                c.execute("INSERT OR IGNORE INTO user_offices (user_id, office_key) VALUES (?,?)", (uid, ok))
            conn.commit()
            flash("Usuário criado.", "success")
            return redirect(url_for("admin_users"))
        except Exception as e:
            conn.rollback()
            flash("Erro ao criar usuário: " + str(e), "error")
            return redirect(url_for("admin_users_create"))
        finally:
            conn.close()
    # GET
    offices = list_offices_meta()
    return render_template("admin_users_create.html", offices=offices)

@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@require_roles("ADMIN")
def admin_users_edit(user_id):
    conn = get_conn()
    c = conn.cursor()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "OPERADOR")
        active = 1 if request.form.get("active") == "1" else 0
        try:
            c.execute("UPDATE users SET full_name=?, role=?, active=? WHERE id=?", (full_name, role, active, user_id))
            conn.commit()
            flash("Usuário atualizado.", "success")
        except Exception as e:
            conn.rollback()
            flash("Erro ao atualizar: " + str(e), "error")
        finally:
            conn.close()
        return redirect(url_for("admin_users"))
    # GET
    c.execute("SELECT id, username, full_name, role, active FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("admin_users"))
    user = {"id": row[0], "username": row[1], "full_name": row[2], "role": row[3], "active": row[4]}
    offices = list_offices_meta()
    user_offs = get_user_offices(user_id)
    return render_template("admin_users_edit.html", user=user, offices=offices, user_offs=user_offs)

@app.route("/admin/users/offices/<int:user_id>", methods=["GET", "POST"])
@require_roles("ADMIN")
def admin_users_offices(user_id):
    if request.method == "POST":
        selected = request.form.getlist("offices")  # list of office keys
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("DELETE FROM user_offices WHERE user_id=?", (user_id,))
            for ok in selected:
                c.execute("INSERT INTO user_offices (user_id, office_key) VALUES (?,?)", (user_id, ok))
            conn.commit()
            flash("Escritórios atribuídos atualizados.", "success")
        except Exception as e:
            conn.rollback()
            flash("Erro ao atualizar escritórios: " + str(e), "error")
        finally:
            conn.close()
        return redirect(url_for("admin_users"))
    offices = list_offices_meta()
    user_offs = get_user_offices(user_id)
    return render_template("admin_users_offices.html", offices=offices, user_offs=user_offs, user_id=user_id)

@app.route("/admin/users/reset_password/<int:user_id>", methods=["POST"])
@require_roles("ADMIN")
def admin_users_reset_password(user_id):
    newpass = request.form.get("new_password", "").strip()
    if not newpass:
        flash("Senha nova obrigatória.", "error")
        return redirect(url_for("admin_users"))
    pw_hash = generate_password_hash(newpass)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))
        conn.commit()
        flash("Senha redefinida.", "success")
    except Exception as e:
        conn.rollback()
        flash("Erro ao redefinir senha: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@require_roles("ADMIN")
def admin_users_delete(user_id):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM user_offices WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        flash("Usuário excluído.", "success")
    except Exception as e:
        conn.rollback()
        flash("Erro ao excluir usuário: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("admin_users"))

# -------------------------
# Client / Office routes (core functionality)
# -------------------------
@app.route("/")
@login_required
def index():
    offices = list_offices_meta()
    return render_template("index.html", offices=offices)

@app.route("/submit", methods=["POST"])
@login_required
@office_edit_allowed
def submit():
    data = request.form
    nome = data.get("nome", "").strip()
    cpf = data.get("cpf", "").strip()
    escritorio_raw = data.get("escritorio", "CENTRAL")
    office_key = normalize_office_raw(escritorio_raw) or "CENTRAL"
    display_name = data.get("escritorio_display") or escritorio_raw.strip().upper() or office_key.replace("_", " ").upper()
    register_office_meta(office_key, display_name)
    table = create_office_table(office_key)
    ensure_table_columns(table)
    tipo_acao = data.get("tipo_acao")
    data_fechamento = data.get("data_fechamento")
    pendencias = data.get("pendencias")
    numero_processo = data.get("numero_processo")
    data_protocolo = data.get("data_protocolo")
    observacoes = data.get("observacoes")
    captador = data.get("captador")
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"""INSERT INTO {table} 
        (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome, cpf, display_name, f"office_{office_key}", tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    flash("Registro salvo com sucesso.", "success")
    return redirect(url_for("table", office=office_key))

@app.route("/table")
@login_required
def table():
    office_param = request.args.get("office", "CENTRAL").strip().upper()
    page = int(request.args.get("page", "1") or 1)
    per_page = int(request.args.get("per_page", "10") or 10)
    if per_page not in (10,20,50,100):
        per_page = 10
    filtro = request.args.get("filtro")
    valor = request.args.get("valor", "").strip()
    data_tipo = request.args.get("data_tipo")
    data_de = request.args.get("data_de")
    data_ate = request.args.get("data_ate")
    offices_meta = list_offices_meta()
    conn = get_conn()
    c = conn.cursor()
    rows = []
    total = 0

    def match_filters(where_parts, params, table_alias="t"):
        if filtro and valor:
            if filtro == "nome":
                where_parts.append(f"LOWER({table_alias}.nome) LIKE ?")
                params.append(f"%{valor.lower()}%")
            elif filtro == "cpf":
                where_parts.append(f"{table_alias}.cpf LIKE ?")
                params.append(f"%{valor}%")
            elif filtro == "id":
                try:
                    _id = int(valor)
                    where_parts.append(f"{table_alias}.id = ?")
                    params.append(_id)
                except:
                    where_parts.append("1=0")
        if data_tipo in ("data_fechamento", "data_protocolo") and (data_de or data_ate):
            if data_de and data_ate:
                where_parts.append(f"{table_alias}.{data_tipo} BETWEEN ? AND ?")
                params.extend([data_de, data_ate])
            elif data_de:
                where_parts.append(f"{table_alias}.{data_tipo} >= ?")
                params.append(data_de)
            elif data_ate:
                where_parts.append(f"{table_alias}.{data_tipo} <= ?")
                params.append(data_ate)

    if office_param == "ALL":
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%' ORDER BY name")
        office_tables = [r[0] for r in c.fetchall()]
        all_rows = []
        for t in office_tables:
            try:
                ensure_table_columns(t)
                where_parts = []
                params = []
                match_filters(where_parts, params, table_alias="t")
                q = f"SELECT * FROM {t}"
                if where_parts:
                    q += " WHERE " + " AND ".join(where_parts)
                q += " ORDER BY id DESC"
                c.execute(q, tuple(params))
                fetched = c.fetchall()
                for fr in fetched:
                    vals = list(fr)
                    while len(vals) < 13:
                        vals.append(None)
                    all_rows.append(tuple(vals[:13]))
            except Exception:
                continue
        total = len(all_rows)
        all_rows.sort(key=lambda x: x[12] or "", reverse=True)
        start = (page-1)*per_page
        rows = all_rows[start:start+per_page]
    else:
        office_key = normalize_office_raw(office_param)
        table = f"office_{office_key}"
        create_office_table(office_key)
        ensure_table_columns(table)
        where_parts = []
        params = []
        match_filters(where_parts, params)
        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)
        try:
            count_q = f"SELECT COUNT(*) FROM {table} {where_sql}"
            c.execute(count_q, tuple(params))
            total = c.fetchone()[0]
        except Exception:
            total = 0
        total_pages = max(1, (total + per_page -1)//per_page)
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        offset = (page - 1) * per_page
        try:
            q = f"SELECT * FROM {table} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
            c.execute(q, tuple(params + [per_page, offset]))
            rows = c.fetchall()
        except Exception:
            rows = []
    conn.close()
    total_pages = max(1, (total + per_page -1)//per_page)
    offices = list_offices_meta()
    return render_template("table.html",
                           rows=rows,
                           office=office_param,
                           offices=offices,
                           page=page,
                           per_page=per_page,
                           total=total,
                           total_pages=total_pages,
                           filtro=filtro,
                           valor=valor,
                           data_tipo=data_tipo,
                           data_de=data_de,
                           data_ate=data_ate)

# Edit/update routes (kept permissive via office_edit_allowed)
@app.route("/edit")
@login_required
def edit():
    registro_id = request.args.get("id")
    office_raw = request.args.get("office", "CENTRAL")
    office_key = normalize_office_raw(office_raw) or "CENTRAL"
    table = f"office_{office_key}"
    ensure_table_columns(table)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
        row = c.fetchone()
    except Exception:
        row = None
    conn.close()
    if not row:
        flash("Registro não encontrado.", "error")
        return redirect(url_for("table", office=office_key))
    cliente = {
        "id": row[0], "nome": row[1], "cpf": row[2], "escritorio_nome": row[3], "escritorio_chave": row[4], "tipo_acao": row[5],
        "data_fechamento": row[6], "pendencias": row[7], "numero_processo": row[8],
        "data_protocolo": row[9], "observacoes": row[10], "captador": row[11], "created_at": row[12] if len(row)>12 else ""
    }
    offices = list_offices_meta()
    return render_template("edit.html", cliente=cliente, office=office_key, offices=offices)

@app.route("/update", methods=["POST"])
@login_required
@office_edit_allowed
def update():
    registro_id = request.form.get("id")
    office_raw = request.form.get("office", "CENTRAL")
    office_key = normalize_office_raw(office_raw) or "CENTRAL"
    table = f"office_{office_key}"
    ensure_table_columns(table)
    nome = request.form.get("nome")
    cpf = request.form.get("cpf")
    escritorio_input = request.form.get("escritorio", "").strip()
    new_office_key = normalize_office_raw(escritorio_input) or office_key
    new_display = escritorio_input.upper() if escritorio_input else get_office_display(new_office_key)
    tipo_acao = request.form.get("tipo_acao")
    data_fechamento = request.form.get("data_fechamento")
    pendencias = request.form.get("pendencias")
    numero_processo = request.form.get("numero_processo")
    data_protocolo = request.form.get("data_protocolo")
    observacoes = request.form.get("observacoes")
    captador = request.form.get("captador")
    conn = get_conn()
    c = conn.cursor()
    try:
        if new_office_key != office_key:
            dest_table = create_office_table(new_office_key)
            ensure_table_columns(dest_table)
            register_office_meta(new_office_key, new_display)
            c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
            old = c.fetchone()
            if old:
                created_at = old[11] if len(old)>11 else datetime.utcnow().isoformat()
                c.execute(f"""INSERT INTO {dest_table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (nome, cpf, new_display, f"office_{new_office_key}", tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at))
                c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
            conn.commit()
            flash("Registro atualizado e movido para novo escritório.", "success")
            return redirect(url_for("table", office=new_office_key))
        else:
            c.execute(f"""
                UPDATE {table}
                SET nome=?, cpf=?, escritorio_nome=?, escritorio_chave=?, tipo_acao=?, data_fechamento=?, pendencias=?, numero_processo=?, data_protocolo=?, observacoes=?, captador=?
                WHERE id=?
            """, (nome, cpf, get_office_display(office_key), f"office_{office_key}", tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, registro_id))
            conn.commit()
            flash("Registro atualizado.", "success")
    except Exception as e:
        flash("Erro ao atualizar registro: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office_key))

# Delete and batch delete (move to excluidos)
@app.route("/delete", methods=["POST"])
@login_required
@office_edit_allowed
def delete():
    registro_id = request.form.get("id")
    office_raw = request.form.get("office", "CENTRAL")
    office_key = normalize_office_raw(office_raw) or "CENTRAL"
    table = f"office_{office_key}"
    ensure_table_columns(table)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
        row = c.fetchone()
        if row:
            escritorio_nome = row[3] if len(row) > 3 and row[3] else get_office_display(office_key)
            escritorio_chave = row[4] if len(row) > 4 and row[4] else f"office_{office_key}"
            c.execute("""INSERT INTO excluidos (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], escritorio_nome, escritorio_chave, row[5] if len(row)>5 else None, row[6] if len(row)>6 else None, row[7] if len(row)>7 else None, row[8] if len(row)>8 else None, row[9] if len(row)>9 else None, row[10] if len(row)>10 else None, row[11] if len(row)>11 else None, row[12] if len(row)>12 else None, datetime.utcnow().isoformat()))
            c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
            conn.commit()
            flash("Registro excluído.", "success")
    except Exception as e:
        flash("Erro ao excluir: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office_key))

@app.route("/delete_selected", methods=["POST"])
@login_required
@office_edit_allowed
def delete_selected():
    ids = request.form.getlist("ids")
    office_raw = request.form.get("office", "CENTRAL")
    office_key = normalize_office_raw(office_raw) or "CENTRAL"
    table = f"office_{office_key}"
    ensure_table_columns(table)
    if not ids:
        flash("Nenhum registro selecionado.", "error")
        return redirect(url_for("table", office=office_key))
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
            row = c.fetchone()
            if row:
                escritorio_nome = row[3] if len(row) > 3 and row[3] else get_office_display(office_key)
                escritorio_chave = row[4] if len(row) > 4 and row[4] else f"office_{office_key}"
                c.execute("""INSERT INTO excluidos (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (row[1], row[2], escritorio_nome, escritorio_chave, row[5] if len(row)>5 else None, row[6] if len(row)>6 else None, row[7] if len(row)>7 else None, row[8] if len(row)>8 else None, row[9] if len(row)>9 else None, row[10] if len(row)>10 else None, row[11] if len(row)>11 else None, row[12] if len(row)>12 else None, datetime.utcnow().isoformat()))
                c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros excluídos.", "success")
    except Exception as e:
        flash("Erro na exclusão em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office_key))

# Excluidos listing (access control: SUPERVISOR and ADMIN can view/restore; OPERADOR cannot view excluidos per your rules)
@app.route("/excluidos")
@login_required
def excluidos():
    user = get_user_by_id(session["user_id"])
    # Visualizador cannot access excluidos; Operators cannot (as per earlier rules)
    if user["role"] == "VISUALIZADOR" or user["role"] == "OPERADOR":
        flash("Você não tem permissão para ver excluídos.", "error")
        return redirect(url_for("index"))
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM excluidos ORDER BY id DESC")
        rows = c.fetchall()
    except Exception:
        rows = []
    conn.close()
    offices = list_offices_meta()
    return render_template("excluidos.html", rows=rows, offices=offices)

# Restore routes (as implemented previously; robust)
@app.route("/restore", methods=["POST"])
@login_required
@require_roles("ADMIN", "SUPERVISOR")
def restore():
    registro_id = request.form.get("id")
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM excluidos WHERE id=?", (registro_id,))
        row = c.fetchone()
        if not row:
            flash("Registro não encontrado.", "error")
            return redirect(url_for("excluidos"))

        nome = row[1]
        cpf = row[2]
        escritorio_nome = row[3] if row[3] else "CENTRAL"
        escritorio_chave = row[4] if row[4] else "office_CENTRAL"
        tipo_acao = row[5]
        data_fechamento = row[6]
        pendencias = row[7]
        numero_processo = row[8]
        data_protocolo = row[9]
        observacoes = row[10]
        captador = row[11]
        created_at = row[12]

        # derive office_key
        if escritorio_chave and escritorio_chave.startswith("office_"):
            office_key = escritorio_chave[len("office_"):].upper()
        else:
            office_key = normalize_office_raw(escritorio_nome) or "CENTRAL"

        table = create_office_table(office_key)
        ensure_table_columns(table)

        c.execute(f"""INSERT INTO {table}
            (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento,
             pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
             (nome, cpf, escritorio_nome, f"office_{office_key}", tipo_acao, data_fechamento,
              pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
        )

        c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registro restaurado com sucesso.", "success")
    except Exception as e:
        flash("Erro ao restaurar: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

@app.route("/restore_selected", methods=["POST"])
@login_required
@require_roles("ADMIN", "SUPERVISOR")
def restore_selected():
    ids = request.form.getlist("ids")
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute("SELECT * FROM excluidos WHERE id=?", (registro_id,))
            row = c.fetchone()
            if not row:
                continue
            nome = row[1]
            cpf = row[2]
            escritorio_nome = row[3] if row[3] else "CENTRAL"
            escritorio_chave = row[4] if row[4] else "office_CENTRAL"
            tipo_acao = row[5]
            data_fechamento = row[6]
            pendencias = row[7]
            numero_processo = row[8]
            data_protocolo = row[9]
            observacoes = row[10]
            captador = row[11]
            created_at = row[12]
            if escritorio_chave and escritorio_chave.startswith("office_"):
                office_key = escritorio_chave[len("office_"):].upper()
            else:
                office_key = normalize_office_raw(escritorio_nome) or "CENTRAL"
            table = create_office_table(office_key)
            ensure_table_columns(table)
            c.execute(f"""INSERT INTO {table}
                (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento,
                 pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (nome, cpf, escritorio_nome, f"office_{office_key}", tipo_acao, data_fechamento,
                  pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
            )
            c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros restaurados com sucesso.", "success")
    except Exception as e:
        flash("Erro ao restaurar registros: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

# Permanent delete from excluidos
@app.route("/delete_forever", methods=["POST"])
@login_required
@require_roles("ADMIN")
def delete_forever():
    registro_id = request.form.get("id")
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registro excluído permanentemente.", "success")
    except Exception as e:
        flash("Erro ao excluir permanentemente: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

@app.route("/delete_forever_selected", methods=["POST"])
@login_required
@require_roles("ADMIN")
def delete_forever_selected():
    ids = request.form.getlist("ids")
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros excluídos permanentemente.", "success")
    except Exception as e:
        flash("Erro ao excluir permanentemente em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

# Migration endpoints (migrate single and batch) - require office permissions
@app.route("/migrate", methods=["POST"])
@login_required
@office_edit_allowed
def migrate():
    registro_id = request.form.get("id")
    from_office_raw = request.form.get("office_current", "CENTRAL")
    target_raw = request.form.get("office_target", "")
    if not target_raw:
        return redirect(url_for("table", office=from_office_raw))
    from_key = normalize_office_raw(from_office_raw) or "CENTRAL"
    to_key = normalize_office_raw(target_raw)
    to_display = target_raw.strip().upper() if target_raw.strip() else to_key.replace("_", " ").upper()
    create_office_table(to_key)
    ensure_table_columns(f"office_{to_key}")
    register_office_meta(to_key, to_display)
    src_table = f"office_{from_key}"
    dest_table = f"office_{to_key}"
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {src_table} WHERE id=?", (registro_id,))
        row = c.fetchone()
        if not row:
            flash("Registro não encontrado.", "error")
            return redirect(url_for("table", office=from_key))
        created_at = row[11] if len(row) > 11 else datetime.utcnow().isoformat()
        c.execute(f"""INSERT INTO {dest_table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (row[1], row[2], to_display, f"office_{to_key}", row[5] if len(row)>5 else None, row[6] if len(row)>6 else None, row[7] if len(row)>7 else None, row[8] if len(row)>8 else None, row[9] if len(row)>9 else None, row[10] if len(row)>10 else None, row[11] if len(row)>11 else created_at))
        c.execute(f"DELETE FROM {src_table} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registro movido com sucesso.", "success")
    except Exception as e:
        flash("Erro ao migrar: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=to_key))

@app.route("/migrate_selected", methods=["POST"])
@login_required
@office_edit_allowed
def migrate_selected():
    ids = request.form.getlist("ids")
    from_office_raw = request.form.get("office_current", "CENTRAL")
    target_raw = request.form.get("office_target", "")
    if not ids or not target_raw:
        flash("Nada selecionado ou destino inválido.", "error")
        return redirect(url_for("table", office=from_office_raw))
    from_key = normalize_office_raw(from_office_raw) or "CENTRAL"
    to_key = normalize_office_raw(target_raw)
    to_display = target_raw.strip().upper() if target_raw.strip() else to_key.replace("_", " ").upper()
    dest_table = create_office_table(to_key)
    ensure_table_columns(dest_table)
    register_office_meta(to_key, to_display)
    src_table = f"office_{from_key}"
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute(f"SELECT * FROM {src_table} WHERE id=?", (registro_id,))
            row = c.fetchone()
            if not row:
                continue
            created_at = row[11] if len(row) > 11 else datetime.utcnow().isoformat()
            c.execute(f"""INSERT INTO {dest_table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], to_display, f"office_{to_key}", row[5] if len(row)>5 else None, row[6] if len(row)>6 else None, row[7] if len(row)>7 else None, row[8] if len(row)>8 else None, row[9] if len(row)>9 else None, row[10] if len(row)>10 else None, row[11] if len(row)>11 else created_at))
            c.execute(f"DELETE FROM {src_table} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros movidos com sucesso.", "success")
    except Exception as e:
        flash("Erro ao migrar em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=to_key))

# Export routes (CSV / PDF) - Admin/Supervisor/Operator/Viz can export, but you can restrict later
@app.route("/export/csv")
@login_required
def export_csv():
    office_param = request.args.get("office", "CENTRAL").upper()
    conn = get_conn()
    c = conn.cursor()
    rows = []
    if office_param == "ALL":
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%'")
        tables = [r[0] for r in c.fetchall()]
        for t in tables:
            try:
                ensure_table_columns(t)
                c.execute(f"SELECT * FROM {t}")
                rows += c.fetchall()
            except:
                continue
    else:
        office_key = normalize_office_raw(office_param)
        table = f"office_{office_key}"
        ensure_table_columns(table)
        try:
            c.execute(f"SELECT * FROM {table}")
            rows = c.fetchall()
        except:
            rows = []
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id","nome","cpf","escritorio_nome","escritorio_chave","tipo_acao","data_fechamento","pendencias","numero_processo","data_protocolo","observacoes","captador","created_at"])
    for r in rows:
        writer.writerow([str(x) for x in r])
    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(mem, as_attachment=True, download_name=f"{office_param}_export.csv", mimetype="text/csv")

@app.route("/export/pdf")
@login_required
def export_pdf():
    office_param = request.args.get("office", "CENTRAL").upper()
    conn = get_conn()
    c = conn.cursor()
    rows = []
    if office_param == "ALL":
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%'")
        tables = [r[0] for r in c.fetchall()]
        for t in tables:
            try:
                ensure_table_columns(t)
                c.execute(f"SELECT * FROM {t}")
                rows += c.fetchall()
            except:
                continue
    else:
        office_key = normalize_office_raw(office_param)
        table = f"office_{office_key}"
        ensure_table_columns(table)
        try:
            c.execute(f"SELECT * FROM {table}")
            rows = c.fetchall()
        except:
            rows = []
    conn.close()
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, f"Registros - Escritório {office_param}")
    y -= 24
    p.setFont("Helvetica", 10)
    for r in rows:
        line = " | ".join(str(x) for x in r[1:6])
        p.drawString(20, y, line)
        y -= 14
        if y < 60:
            p.showPage()
            y = 750
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{office_param}_export.pdf", mimetype="application/pdf")

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    # ensure default admin exists before app runs
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
