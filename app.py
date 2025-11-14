from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import sqlite3
import os
import io
import csv
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_FILE = os.path.join(BASE_DIR, 'database.db')

# ---------------------------------------------------------
#  BANCO DE DADOS
# ---------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # tabela principal da central
    c.execute("""
        CREATE TABLE IF NOT EXISTS office_Central (
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

    # tabela de clientes excluídos
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

# ---------------------------------------------------------
#  INICIALIZAÇÃO DO FLASK
# ---------------------------------------------------------

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "chave_segura"

# chama init_db NO MOMENTO CORRETO
init_db()

# ---------------------------------------------------------
#  ROTAS PRINCIPAIS
# ---------------------------------------------------------

@app.route("/")
def home():
    return redirect(url_for("index"))

@app.route("/index")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    data = request.form
    office = data.get("escritorio", "Central").strip() or "Central"
    table = f"office_{office.replace(' ', '_')}"

    conn = get_conn()
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

    c.execute(f"""
        INSERT INTO {table} 
        (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("nome"),
        data.get("cpf"),
        office,
        data.get("tipo_acao"),
        data.get("data_fechamento"),
        data.get("pendencias"),
        data.get("numero_processo"),
        data.get("data_protocolo"),
        data.get("observacoes"),
        data.get("captador"),
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()
    flash("Registro salvo com sucesso!", "success")
    return redirect(url_for("table", office=office))

@app.route("/table")
def table():
    office = request.args.get("office", "Central")
    table = f"office_{office.replace(' ', '_')}"

    conn = get_conn()
    c = conn.cursor()
    try:
        rows = c.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
    except:
        rows = []
    conn.close()

    return render_template("table.html", rows=rows, office=office)

# ---------------------------------------------------------
#  EXCLUSÃO INDIVIDUAL
# ---------------------------------------------------------

@app.route("/delete", methods=["POST"])
def delete():
    table = request.form.get("table")
    id_ = request.form.get("id")

    if not table or not id_:
        flash("Erro ao excluir registro.", "error")
        return redirect(url_for("table"))

    conn = get_conn()
    c = conn.cursor()

    c.execute(f"SELECT * FROM {table} WHERE id=?", (id_,))
    row = c.fetchone()

    if row:
        c.execute("""
            INSERT INTO excluidos 
            (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["nome"], row["cpf"], table,
            row["tipo_acao"], row["data_fechamento"], row["pendencias"],
            row["numero_processo"], row["data_protocolo"], row["observacoes"],
            row["captador"], row["created_at"], datetime.utcnow().isoformat()
        ))

        c.execute(f"DELETE FROM {table} WHERE id=?", (id_,))

    conn.commit()
    conn.close()

    flash("Registro excluído com sucesso!", "success")
    return redirect(url_for("table", office=table.replace("office_", "")))

# ---------------------------------------------------------
#  EXCLUSÃO MÚLTIPLA
# ---------------------------------------------------------

@app.route("/delete_selected", methods=["POST"])
def delete_selected():
    ids = request.form.getlist("ids")
    office = request.form.get("office", "Central")
    table = f"office_{office.replace(' ', '_')}"

    if not ids:
        flash("Nenhum registro selecionado.", "error")
        return redirect(url_for("table", office=office))

    conn = get_conn()
    c = conn.cursor()

    for id_ in ids:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (id_,))
        row = c.fetchone()

        if row:
            c.execute("""
                INSERT INTO excluidos 
                (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["nome"], row["cpf"], table,
                row["tipo_acao"], row["data_fechamento"], row["pendencias"],
                row["numero_processo"], row["data_protocolo"], row["observacoes"],
                row["captador"], row["created_at"], datetime.utcnow().isoformat()
            ))

            c.execute(f"DELETE FROM {table} WHERE id=?", (id_,))

    conn.commit()
    conn.close()
    flash("Registros excluídos com sucesso!", "success")
    return redirect(url_for("table", office=office))

# ---------------------------------------------------------
#  VER EXCLUÍDOS
# ---------------------------------------------------------

@app.route("/excluidos")
def excluidos():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM excluidos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("excluidos.html", rows=rows)

# ---------------------------------------------------------
#  RESTAURAR INDIVIDUAL
# ---------------------------------------------------------

@app.route("/restore", methods=["POST"])
def restore():
    id_ = request.form.get("id")

    if not id_:
        flash("Erro ao restaurar.", "error")
        return redirect(url_for("excluidos"))

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM excluidos WHERE id=?", (id_,))
    row = c.fetchone()

    if row:
        table = row["escritorio_origem"]

        c.execute(f"""
            INSERT INTO {table}
            (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["nome"], row["cpf"], table.replace("office_", ""),
            row["tipo_acao"], row["data_fechamento"], row["pendencias"],
            row["numero_processo"], row["data_protocolo"], row["observacoes"],
            row["captador"], row["created_at"]
        ))

        c.execute("DELETE FROM excluidos WHERE id=?", (id_,))

    conn.commit()
    conn.close()
    flash("Registro restaurado!", "success")
    return redirect(url_for("excluidos"))

# ---------------------------------------------------------
#  RESTAURAR MÚLTIPLOS
# ---------------------------------------------------------

@app.route("/restore_selected", methods=["POST"])
def restore_selected():
    ids = request.form.getlist("ids")

    if not ids:
        flash("Nenhum registro selecionado.", "error")
        return redirect(url_for("excluidos"))

    conn = get_conn()
    c = conn.cursor()

    for id_ in ids:
        c.execute("SELECT * FROM excluidos WHERE id=?", (id_,))
        row = c.fetchone()

        if row:
            table = row["escritorio_origem"]

            c.execute(f"""
                INSERT INTO {table}
                (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["nome"], row["cpf"], table.replace("office_", ""),
                row["tipo_acao"], row["data_fechamento"], row["pendencias"],
                row["numero_processo"], row["data_protocolo"], row["observacoes"],
                row["captador"], row["created_at"]
            ))

            c.execute("DELETE FROM excluidos WHERE id=?", (id_,))

    conn.commit()
    conn.close()
    flash("Registros restaurados!", "success")
    return redirect(url_for("excluidos"))

# ---------------------------------------------------------
#  EXPORTAÇÃO CSV E PDF
# ---------------------------------------------------------

@app.route("/export/csv")
def export_csv():
    office = request.args.get("office", "Central")

    conn = get_conn()
    c = conn.cursor()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    if office.lower() == "all":
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    elif office.lower() == "excluidos":
        tables = ["excluidos"]
    else:
        tables = [f"office_{office.replace(' ', '_')}"]

    for t in tables:
        writer.writerow([f"Tabela: {t}"])
        try:
            for row in c.execute(f"SELECT * FROM {t}"):
                writer.writerow([str(x) for x in row])
        except:
            writer.writerow(["<erro lendo tabela>"])
        writer.writerow([])

    conn.close()

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(mem, as_attachment=True, download_name=f"{office}_export.csv", mimetype="text/csv")

@app.route("/export/pdf")
def export_pdf():
    office = request.args.get("office", "Central")

    conn = get_conn()
    c = conn.cursor()

    if office.lower() == "all":
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    elif office.lower() == "excluidos":
        tables = ["excluidos"]
    else:
        tables = [f"office_{office.replace(' ', '_')}"]

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 60

    p.setFont("Helvetica-Bold", 14)
    p.drawString(60, y, "Relatório de Registros")
    y -= 25

    for t in tables:
        p.setFont("Helvetica-Bold", 12)
        p.drawString(40, y, f"Tabela: {t}")
        y -= 16

        try:
            for row in c.execute(f"SELECT nome, cpf, escritorio, tipo_acao FROM {t}"):
                if y < 80:
                    p.showPage()
                    y = height - 60

                p.setFont("Helvetica", 10)
                p.drawString(50, y, " | ".join([str(x) for x in row]))
                y -= 14
        except:
            p.drawString(50, y, "(erro lendo tabela)")
            y -= 14

        y -= 20

    p.save()
    buffer.seek(0)
    conn.close()

    return send_file(buffer, as_attachment=True, download_name=f"{office}_export.pdf", mimetype="application/pdf")

# ---------------------------------------------------------
#  EXECUÇÃO LOCAL
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
