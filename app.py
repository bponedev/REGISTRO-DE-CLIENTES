from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# ---------------------------------------------------
# CONFIGURAÇÃO E INICIALIZAÇÃO
# ---------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = "troque-esta-chave"

# ---------------------------------------------------
# FUNÇÃO PARA INICIALIZAR BANCO
# ---------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

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

    conn.commit()
    conn.close()

init_db()  # render executa aqui

# ---------------------------------------------------
# FUNÇÃO PARA CRIAR TABELAS DE ESCRITÓRIO
# ---------------------------------------------------

def create_office_table(office):
    table = f"office_{office}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
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

    conn.commit()
    conn.close()
    return table

# ---------------------------------------------------
# ROTA: INÍCIO (CADASTRAR CLIENTE)
# ---------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

# ---------------------------------------------------
# ROTA: SALVAR CADASTRO
# ---------------------------------------------------

@app.route("/submit", methods=["POST"])
def submit():
    nome = request.form["nome"]
    cpf = request.form["cpf"]
    escritorio = request.form["escritorio"].replace(" ", "_").lower()
    tipo_acao = request.form["tipo_acao"]
    data_fechamento = request.form["data_fechamento"]
    pendencias = request.form["pendencias"]
    numero_processo = request.form["numero_processo"]
    data_protocolo = request.form["data_protocolo"]
    observacoes = request.form["observacoes"]
    captador = request.form["captador"]

    table = create_office_table(escritorio)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        f"""INSERT INTO {table} 
        (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias,
            numero_processo, data_protocolo, observacoes, captador,
            datetime.utcnow().isoformat()
        )
    )
    conn.commit()
    conn.close()

    return redirect(url_for("table", office=escritorio))

# ---------------------------------------------------
# ROTA: LISTAR CLIENTES
# ---------------------------------------------------

@app.route("/table")
def table():
    office = request.args.get("office")
    if not office:
        office = "central"

    office_clean = office.replace(" ", "_").lower()
    table_name = create_office_table(office_clean)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table_name} ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    return render_template("table.html", rows=rows, office=office_clean)

# ---------------------------------------------------
# ROTA: EDITAR CLIENTE (TELA)
# ---------------------------------------------------

@app.route("/edit")
def edit():
    registro_id = request.args.get("id")
    office = request.args.get("office")
    table = f"office_{office}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "Cliente não encontrado", 404

    cliente = {
        "id": row[0],
        "nome": row[1],
        "cpf": row[2],
        "escritorio": row[3],
        "tipo_acao": row[4],
        "data_fechamento": row[5],
        "pendencias": row[6],
        "numero_processo": row[7],
        "data_protocolo": row[8],
        "observacoes": row[9],
        "captador": row[10],
        "created_at": row[11]
    }

    return render_template("edit.html", cliente=cliente, office=office)

# ---------------------------------------------------
# ROTA: SALVAR ALTERAÇÕES DO CLIENTE
# ---------------------------------------------------

@app.route("/update", methods=["POST"])
def update():
    registro_id = request.form["id"]
    office = request.form["office"]
    table = f"office_{office}"

    nome = request.form["nome"]
    cpf = request.form["cpf"]
    escritorio = request.form["escritorio"]
    tipo_acao = request.form["tipo_acao"]
    data_fechamento = request.form["data_fechamento"]
    pendencias = request.form["pendencias"]
    numero_processo = request.form["numero_processo"]
    data_protocolo = request.form["data_protocolo"]
    observacoes = request.form["observacoes"]
    captador = request.form["captador"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"""
        UPDATE {table}
        SET nome=?, cpf=?, escritorio=?, tipo_acao=?, data_fechamento=?,
            pendencias=?, numero_processo=?, data_protocolo=?, observacoes=?, captador=?
        WHERE id=?
    """, (
        nome, cpf, escritorio, tipo_acao, data_fechamento,
        pendencias, numero_processo, data_protocolo,
        observacoes, captador, registro_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("table", office=office))

# ---------------------------------------------------
# ROTA: EXCLUIR CLIENTE (INDIVIDUAL)
# ---------------------------------------------------

@app.route("/delete", methods=["POST"])
def delete():
    registro_id = request.form["id"]
    office = request.form["office"]
    table = f"office_{office}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
    row = c.fetchone()

    if row:
        c.execute("""
            INSERT INTO excluidos
            (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo,
             data_protocolo, observacoes, captador, created_at, data_exclusao)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row[1], row[2], office, row[4], row[5], row[6], row[7],
            row[8], row[9], row[10], row[11], datetime.utcnow().isoformat()
        ))

    c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("table", office=office))

# ---------------------------------------------------
# ROTA: EXCLUIR MÚLTIPLOS
# ---------------------------------------------------

@app.route("/delete_selected", methods=["POST"])
def delete_selected():
    ids = request.form.getlist("ids")
    office = request.form["office"]
    table = f"office_{office}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for registro_id in ids:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
        row = c.fetchone()

        if row:
            c.execute("""
                INSERT INTO excluidos
                (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo,
                 data_protocolo, observacoes, captador, created_at, data_exclusao)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row[1], row[2], office, row[4], row[5], row[6], row[7],
                row[8], row[9], row[10], row[11], datetime.utcnow().isoformat()
            ))

        c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("table", office=office))

# ---------------------------------------------------
# ROTA: VER EXCLUÍDOS
# ---------------------------------------------------

@app.route("/excluidos")
def excluidos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM excluidos ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template("excluidos.html", rows=rows)

# ---------------------------------------------------
# ROTA: RESTAURAR REGISTRO
# ---------------------------------------------------

@app.route("/restore", methods=["POST"])
def restore():
    registro_id = request.form["id"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT * FROM excluidos WHERE id=?", (registro_id,))
    row = c.fetchone()

    if row:
        office = row[3].replace(" ", "_").lower()
        table = create_office_table(office)

        c.execute(f"""
            INSERT INTO {table}
            (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias,
             numero_processo, data_protocolo, observacoes, captador, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row[1], row[2], office, row[4], row[5], row[6], row[7],
            row[8], row[9], row[10], row[11]
        ))

        c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("excluidos"))

# ---------------------------------------------------
# ROTA: EXPORT CSV
# ---------------------------------------------------

@app.route("/export_csv")
def export_csv():
    office = request.args.get("office", "central").lower()
    table = f"office_{office}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    rows = c.fetchall()
    conn.close()

    csv_path = os.path.join(BASE_DIR, f"{office}_registros.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("id;nome;cpf;escritorio;tipo_acao;data_fechamento;pendencias;numero_processo;data_protocolo;observacoes;captador;created_at\n")
        for r in rows:
            f.write(";".join(str(x) for x in r) + "\n")

    return send_file(csv_path, as_attachment=True)

# ---------------------------------------------------
# ROTA: EXPORT PDF
# ---------------------------------------------------

@app.route("/export_pdf")
def export_pdf():
    office = request.args.get("office", "central").lower()
    table = f"office_{office}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    rows = c.fetchall()
    conn.close()

    pdf_path = os.path.join(BASE_DIR, f"{office}_registros.pdf")
    pdf = canvas.Canvas(pdf_path, pagesize=letter)
    pdf.drawString(50, 750, f"Registros - Escritório {office}")

    y = 720
    for r in rows:
        pdf.drawString(20, y, f"{r}")
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()

    return send_file(pdf_path, as_attachment=True)

# ---------------------------------------------------
# INICIALIZAÇÃO LOCAL
# ---------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
