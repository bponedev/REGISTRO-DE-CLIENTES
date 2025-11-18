import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "chave-super-secreta"

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


# -----------------------------------------------------
#  BANCO DE DADOS – conexão
# -----------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------------------------------
#  CRIAR TABELAS
# -----------------------------------------------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    # REGISTROS
    c.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cpf TEXT,
            escritorio TEXT,
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

    # EXCLUÍDOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS excluidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cpf TEXT,
            escritorio_origem TEXT,
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

    # ESCRITÓRIOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS offices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    """)

    # USUÁRIOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            senha TEXT,
            nome TEXT,
            role TEXT,
            ativo INTEGER DEFAULT 1
        )
    """)

    # ATRIBUIÇÃO DE USUÁRIOS A ESCRITÓRIOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_offices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            office_name TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Criar "CENTRAL" automaticamente
    c.execute("INSERT OR IGNORE INTO offices (nome) VALUES ('CENTRAL')")

    # Criar admin padrão
    c.execute("INSERT OR IGNORE INTO users (username, senha, nome, role) VALUES ('admin','admin','Administrador','ADMIN')")

    conn.commit()
    conn.close()


init_db()


# -----------------------------------------------------
#  LOGIN / LOGOUT
# -----------------------------------------------------
def login_required(role=None):
    def wrapper(fn):
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if role:
                if session.get("role") not in role:
                    flash("Acesso não permitido.", "error")
                    return redirect(url_for("index"))

            return fn(*args, **kwargs)
        decorated.__name__ = fn.__name__
        return decorated
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        senha = request.form["senha"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND senha=? AND ativo=1", (username, senha))
        user = c.fetchone()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha incorretos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------------------------------
#  NOVO CADASTRO
# -----------------------------------------------------
@app.route("/")
@login_required(role=["ADMIN", "SUPERVISOR", "OPERADOR"])
def index():
    conn = get_db()
    offices = conn.execute("SELECT nome FROM offices ORDER BY nome").fetchall()
    return render_template("index.html", offices=offices)


@app.route("/submit", methods=["POST"])
@login_required(role=["ADMIN", "SUPERVISOR", "OPERADOR"])
def submit():
    data = (
        request.form["nome"],
        request.form["cpf"],
        request.form["escritorio"],
        request.form["tipo_acao"],
        request.form["data_fechamento"],
        request.form["pendencias"],
        request.form["numero_processo"],
        request.form["data_protocolo"],
        request.form["observacoes"],
        request.form["captador"],
        datetime.utcnow().isoformat()
    )

    conn = get_db()
    conn.execute("""
        INSERT INTO registros (
            nome, cpf, escritorio, tipo_acao, data_fechamento,
            pendencias, numero_processo, data_protocolo,
            observacoes, captador, created_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, data)

    conn.commit()
    flash("Registro criado com sucesso!", "success")
    return redirect(url_for("index"))


# -----------------------------------------------------
#  LISTAGEM / FILTROS / BUSCA / PAGINAÇÃO
# -----------------------------------------------------
@app.route("/table")
@login_required(role=["ADMIN", "SUPERVISOR", "OPERADOR", "VISUALIZADOR"])
def table():
    office = request.args.get("office", "CENTRAL")
    search = request.args.get("search", "")
    filter_field = request.args.get("field", "nome")

    conn = get_db()
    offices = conn.execute("SELECT nome FROM offices ORDER BY nome").fetchall()

    query = "SELECT * FROM registros WHERE 1=1"
    params = []

    if office != "TODOS":
        query += " AND escritorio=?"
        params.append(office)

    if search:
        query += f" AND {filter_field} LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY id DESC"

    rows = conn.execute(query, tuple(params)).fetchall()

    return render_template("table.html", rows=rows, offices=offices, office_selected=office)


# -----------------------------------------------------
#  EXCLUIR (ENVIA PARA A LIXEIRA)
# -----------------------------------------------------
@app.route("/delete/<int:id>")
@login_required(role=["ADMIN", "SUPERVISOR"])
def delete(id):
    conn = get_db()
    c = conn.cursor()

    row = c.execute("SELECT * FROM registros WHERE id=?", (id,)).fetchone()
    if not row:
        flash("Registro não encontrado.", "error")
        return redirect(url_for("table"))

    c.execute("""
        INSERT INTO excluidos (
            nome, cpf, escritorio_origem, tipo_acao, data_fechamento,
            pendencias, numero_processo, data_protocolo, observacoes,
            captador, created_at, data_exclusao
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["nome"], row["cpf"], row["escritorio"], row["tipo_acao"], row["data_fechamento"],
        row["pendencias"], row["numero_processo"], row["data_protocolo"],
        row["observacoes"], row["captador"], row["created_at"],
        datetime.utcnow().isoformat()
    ))

    c.execute("DELETE FROM registros WHERE id=?", (id,))
    conn.commit()

    flash("Registro movido para excluídos.", "warning")
    return redirect(url_for("table", office=row["escritorio"]))


# -----------------------------------------------------
#  PÁGINA DE EXCLUÍDOS
# -----------------------------------------------------
@app.route("/excluidos")
@login_required(role=["ADMIN", "SUPERVISOR"])
def excluidos():
    conn = get_db()
    rows = conn.execute("SELECT * FROM excluidos ORDER BY id DESC").fetchall()
    offices = conn.execute("SELECT nome FROM offices ORDER BY nome").fetchall()
    return render_template("excluidos.html", rows=rows, offices=offices)


# -----------------------------------------------------
#  RESTAURAR
# -----------------------------------------------------
@app.route("/restore/<int:id>")
@login_required(role=["ADMIN", "SUPERVISOR"])
def restore(id):
    conn = get_db()
    c = conn.cursor()

    row = c.execute("SELECT * FROM excluidos WHERE id=?", (id,)).fetchone()
    if not row:
        flash("Registro não encontrado.", "error")
        return redirect(url_for("excluidos"))

    c.execute("""
        INSERT INTO registros (
            nome, cpf, escritorio, tipo_acao, data_fechamento,
            pendencias, numero_processo, data_protocolo,
            observacoes, captador, created_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["nome"], row["cpf"], row["escritorio_origem"], row["tipo_acao"], row["data_fechamento"],
        row["pendencias"], row["numero_processo"], row["data_protocolo"],
        row["observacoes"], row["captador"], row["created_at"]
    ))

    c.execute("DELETE FROM excluidos WHERE id=?", (id,))
    conn.commit()

    flash("Registro restaurado com sucesso!", "success")
    return redirect(url_for("excluidos"))


# -----------------------------------------------------
#  EDITAR REGISTRO
# -----------------------------------------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required(role=["ADMIN", "SUPERVISOR", "OPERADOR"])
def edit(id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            UPDATE registros SET nome=?, cpf=?, escritorio=?, tipo_acao=?, 
                data_fechamento=?, pendencias=?, numero_processo=?, 
                data_protocolo=?, observacoes=?, captador=?
            WHERE id=?
        """, (
            request.form["nome"], request.form["cpf"], request.form["escritorio"],
            request.form["tipo_acao"], request.form["data_fechamento"],
            request.form["pendencias"], request.form["numero_processo"],
            request.form["data_protocolo"], request.form["observacoes"],
            request.form["captador"], id
        ))

        conn.commit()
        flash("Registro atualizado!", "success")
        return redirect(url_for("table"))

    offices = conn.execute("SELECT nome FROM offices ORDER BY nome").fetchall()
    row = conn.execute("SELECT * FROM registros WHERE id=?", (id,)).fetchone()
    return render_template("edit.html", row=row, offices=offices)


# -----------------------------------------------------
#  ESCRITÓRIOS – GERENCIAR
# -----------------------------------------------------
@app.route("/offices")
@login_required(role=["ADMIN", "SUPERVISOR"])
def offices():
    conn = get_db()
    rows = conn.execute("SELECT * FROM offices ORDER BY nome").fetchall()
    return render_template("offices.html", rows=rows)


@app.route("/offices/create", methods=["POST"])
@login_required(role=["ADMIN", "SUPERVISOR"])
def offices_create():
    nome = request.form["nome"].upper()

    conn = get_db()
    try:
        conn.execute("INSERT INTO offices (nome) VALUES (?)", (nome,))
        conn.commit()
        flash("Escritório criado!", "success")
    except:
        flash("Nome já existe.", "error")

    return redirect(url_for("offices"))


@app.route("/offices/delete/<int:id>")
@login_required(role=["ADMIN"])
def offices_delete(id):
    conn = get_db()
    conn.execute("DELETE FROM offices WHERE id=?", (id,))
    conn.commit()

    flash("Escritório removido.", "warning")
    return redirect(url_for("offices"))


# -----------------------------------------------------
#  ADMIN – LISTA DE USUÁRIOS
# -----------------------------------------------------
@app.route("/admin/users")
@login_required(role=["ADMIN"])
def admin_users():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/create", methods=["GET", "POST"])
@login_required(role=["ADMIN"])
def admin_users_create():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO users (username, senha, nome, role)
            VALUES (?,?,?,?)
        """, (
            request.form["username"], request.form["senha"],
            request.form["nome"], request.form["role"]
        ))
        conn.commit()
        flash("Usuário criado!", "success")
        return redirect(url_for("admin_users"))

    offices = conn.execute("SELECT nome FROM offices").fetchall()
    return render_template("admin_users_create.html", offices=offices)


@app.route("/admin/users/edit/<int:id>", methods=["GET", "POST"])
@login_required(role=["ADMIN"])
def admin_users_edit(id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            UPDATE users SET nome=?, role=?, ativo=?
            WHERE id=?
        """, (
            request.form["nome"], request.form["role"],
            request.form.get("ativo", 0), id
        ))
        conn.commit()
        flash("Usuário atualizado!", "success")
        return redirect(url_for("admin_users"))

    user = conn.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    return render_template("admin_users_edit.html", user=user)


@app.route("/admin/users/offices/<int:id>", methods=["GET", "POST"])
@login_required(role=["ADMIN"])
def admin_users_offices(id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("DELETE FROM user_offices WHERE user_id=?", (id,))
        for office in request.form.getlist("office"):
            conn.execute("INSERT INTO user_offices (user_id, office_name) VALUES (?,?)", (id, office))
        conn.commit()
        flash("Escritórios atribuídos!", "success")
        return redirect(url_for("admin_users"))

    user = conn.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    offices = conn.execute("SELECT nome FROM offices").fetchall()
    assigned = conn.execute("SELECT office_name FROM user_offices WHERE user_id=?", (id,)).fetchall()

    assigned_list = [a["office_name"] for a in assigned]

    return render_template("admin_users_offices.html",
                           user=user, offices=offices, assigned=assigned_list)


# -----------------------------------------------------
#  INICIAR SERVIDOR
# -----------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
