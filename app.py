from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import sqlite3
import os
import io
import csv
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# -------------------------
# Config
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "troque_para_uma_chave_secreta"

# -------------------------
# Helpers - DB
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = None  # keep default tuple rows (templates use r[0], r[1], ...)
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # excluidos
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

def create_office_table(office_key):
    """office_key: normalized key like 'central' or 'campos' (no prefix)"""
    table = f"office_{office_key}"
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
    conn.commit()
    conn.close()
    return table

def list_offices():
    """Return list of office keys (normalized) found in DB, includes 'central' by default."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%'")
    rows = c.fetchall()
    conn.close()
    offices = []
    for r in rows:
        name = r[0]  # e.g. 'office_central'
        key = name[len("office_"):].lower()
        offices.append(key)
    # ensure 'central' exists in the list
    if 'central' not in offices:
        offices.insert(0, 'central')
    # unique preserve order
    seen = set()
    out = []
    for o in offices:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out

# Initialize DB/tables
init_db()

# -------------------------
# Routes
# -------------------------

@app.route("/")
def index():
    offices = list_offices()
    return render_template("index.html", offices=offices)

# Submit new client
@app.route("/submit", methods=["POST"])
def submit():
    data = request.form
    nome = data.get("nome", "").strip()
    cpf = data.get("cpf", "").strip()
    escritorio_raw = data.get("escritorio", "central").strip()
    office = escritorio_raw.replace(" ", "_").lower() or "central"
    tipo_acao = data.get("tipo_acao")
    data_fechamento = data.get("data_fechamento")
    pendencias = data.get("pendencias")
    numero_processo = data.get("numero_processo")
    data_protocolo = data.get("data_protocolo")
    observacoes = data.get("observacoes")
    captador = data.get("captador")

    table = create_office_table(office)

    conn = get_conn()
    c = conn.cursor()
    c.execute(f"""INSERT INTO {table} 
        (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome, cpf, office, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    flash("Registro salvo com sucesso.", "success")
    return redirect(url_for("table", office=office))

# Table listing with pagination, search, date filters
@app.route("/table")
def table():
    # params
    office = request.args.get("office", "central").strip() or "central"
    office = office.replace(" ", "_").lower()
    page = int(request.args.get("page", "1") or 1)
    per_page = int(request.args.get("per_page", "10") or 10)
    if per_page not in (10, 20, 50, 100):
        per_page = 10

    # search/filter params
    filtro = request.args.get("filtro")  # 'nome'|'cpf'|'id' or None
    valor = request.args.get("valor", "").strip()
    data_tipo = request.args.get("data_tipo")  # 'data_fechamento' or 'data_protocolo'
    data_de = request.args.get("data_de")
    data_ate = request.args.get("data_ate")

    table_name = create_office_table(office)  # ensure table exists

    # build where clause safely
    where_clauses = []
    params = []

    if filtro and valor:
        if filtro == "nome":
            where_clauses.append("LOWER(nome) LIKE ?")
            params.append(f"%{valor.lower()}%")
        elif filtro == "cpf":
            where_clauses.append("cpf LIKE ?")
            params.append(f"%{valor}%")
        elif filtro == "id":
            # exact match if integer
            try:
                _id = int(valor)
                where_clauses.append("id = ?")
                params.append(_id)
            except:
                # invalid id -> no results
                where_clauses.append("1 = 0")

    if data_tipo in ("data_fechamento", "data_protocolo") and (data_de or data_ate):
        # add date range conditions
        if data_de and data_ate:
            where_clauses.append(f"{data_tipo} BETWEEN ? AND ?")
            params.append(data_de)
            params.append(data_ate)
        elif data_de:
            where_clauses.append(f"{data_tipo} >= ?")
            params.append(data_de)
        elif data_ate:
            where_clauses.append(f"{data_tipo} <= ?")
            params.append(data_ate)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    conn = get_conn()
    c = conn.cursor()

    # total count for pagination
    try:
        count_q = f"SELECT COUNT(*) FROM {table_name} {where_sql}"
        c.execute(count_q, tuple(params))
        total = c.fetchone()[0]
    except Exception:
        total = 0

    # compute pagination
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    # fetch rows with limit
    rows = []
    try:
        q = f"SELECT * FROM {table_name} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
        q_params = params + [per_page, offset]
        c.execute(q, tuple(q_params))
        rows = c.fetchall()
    except Exception:
        rows = []

    conn.close()

    offices = list_offices()
    # render template (templates should reference rows as r[0], r[1], ...)
    return render_template(
        "table.html",
        rows=rows,
        office=office,
        offices=offices,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        filtro=filtro,
        valor=valor,
        data_tipo=data_tipo,
        data_de=data_de,
        data_ate=data_ate
    )

# Edit - show form
@app.route("/edit")
def edit():
    registro_id = request.args.get("id")
    office = request.args.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
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
        return redirect(url_for("table", office=office))
    cliente = {
        "id": row[0], "nome": row[1], "cpf": row[2], "escritorio": row[3], "tipo_acao": row[4],
        "data_fechamento": row[5], "pendencias": row[6], "numero_processo": row[7],
        "data_protocolo": row[8], "observacoes": row[9], "captador": row[10], "created_at": row[11]
    }
    offices = list_offices()
    return render_template("edit.html", cliente=cliente, office=office, offices=offices)

# Update (save edits)
@app.route("/update", methods=["POST"])
def update():
    registro_id = request.form.get("id")
    office = request.form.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
    nome = request.form.get("nome")
    cpf = request.form.get("cpf")
    escritorio = request.form.get("escritorio").replace(" ", "_").lower()
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
        c.execute(f"""
            UPDATE {table}
            SET nome=?, cpf=?, escritorio=?, tipo_acao=?, data_fechamento=?, pendencias=?, numero_processo=?, data_protocolo=?, observacoes=?, captador=?
            WHERE id=?
        """, (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, registro_id))
        conn.commit()
    except Exception as e:
        flash("Erro ao atualizar registro: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office))

# Delete individual (move to excluidos)
@app.route("/delete", methods=["POST"])
def delete():
    registro_id = request.form.get("id")
    office = request.form.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
        row = c.fetchone()
        if row:
            c.execute("""INSERT INTO excluidos (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], table, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], datetime.utcnow().isoformat()))
            c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
            conn.commit()
            flash("Registro excluído.", "success")
    except Exception as e:
        flash("Erro ao excluir: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office))

# Delete selected (batch)
@app.route("/delete_selected", methods=["POST"])
def delete_selected():
    ids = request.form.getlist("ids")
    office = request.form.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
    if not ids:
        flash("Nenhum registro selecionado.", "error")
        return redirect(url_for("table", office=office))
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
            row = c.fetchone()
            if row:
                c.execute("""INSERT INTO excluidos (nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (row[1], row[2], table, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], datetime.utcnow().isoformat()))
                c.execute(f"DELETE FROM {table} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros excluídos.", "success")
    except Exception as e:
        flash("Erro na exclusão em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office))

# Excluídos listing
@app.route("/excluidos")
def excluidos():
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM excluidos ORDER BY id DESC")
        rows = c.fetchall()
    except Exception:
        rows = []
    conn.close()
    return render_template("excluidos.html", rows=rows, offices=list_offices())

# Restore individual
@app.route("/restore", methods=["POST"])
def restore():
    registro_id = request.form.get("id")
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM excluidos WHERE id=?", (registro_id,))
        row = c.fetchone()
        if row:
            # row structure: id, nome, cpf, escritorio_origem, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at, data_exclusao
            origem = row[3] or "office_central"
            # origem may be stored as 'office_xxx' -> unify it
            if origem.startswith("office_"):
                table = origem
                office_key = origem[len("office_"):]
            else:
                table = f"office_{origem.replace(' ', '_').lower()}"
                office_key = origem.replace(" ", "_").lower()
            create_office_table(office_key)
            c.execute(f"""INSERT INTO {table} (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], office_key, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11]))
            c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
            conn.commit()
            flash("Registro restaurado.", "success")
    except Exception as e:
        flash("Erro ao restaurar: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

# Restore selected (batch)
@app.route("/restore_selected", methods=["POST"])
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
            origem = row[3] or "office_central"
            if origem.startswith("office_"):
                table = origem
                office_key = origem[len("office_"):]
            else:
                office_key = origem.replace(" ", "_").lower()
                table = f"office_{office_key}"
            create_office_table(office_key)
            c.execute(f"""INSERT INTO {table} (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], office_key, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11]))
            c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros restaurados.", "success")
    except Exception as e:
        flash("Erro ao restaurar em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

# -------------------------
# Migration endpoints (move record to another office)
# -------------------------
@app.route("/migrate", methods=["POST"])
def migrate():
    """migrate single record: expects id and office_current and office_target"""
    registro_id = request.form.get("id")
    office_current = request.form.get("office_current", "central").replace(" ", "_").lower()
    office_target = request.form.get("office_target", "").replace(" ", "_").lower()
    if not office_target:
        flash("Destino inválido.", "error")
        return redirect(url_for("table", office=office_current))
    table_src = f"office_{office_current}"
    table_dest = create_office_table(office_target)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table_src} WHERE id=?", (registro_id,))
        row = c.fetchone()
        if not row:
            flash("Registro não encontrado.", "error")
            return redirect(url_for("table", office=office_current))
        # insert into dest
        c.execute(f"""INSERT INTO {table_dest} (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (row[1], row[2], office_target, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11]))
        # delete from src
        c.execute(f"DELETE FROM {table_src} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registro movido com sucesso.", "success")
    except Exception as e:
        flash("Erro ao migrar: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office_target))

@app.route("/migrate_selected", methods=["POST"])
def migrate_selected():
    """migrate multiple selected ids from office_current to office_target"""
    ids = request.form.getlist("ids")
    office_current = request.form.get("office_current", "central").replace(" ", "_").lower()
    office_target = request.form.get("office_target", "").replace(" ", "_").lower()
    if not ids or not office_target:
        flash("Nada selecionado ou destino inválido.", "error")
        return redirect(url_for("table", office=office_current))
    table_src = f"office_{office_current}"
    table_dest = create_office_table(office_target)
    conn = get_conn()
    c = conn.cursor()
    try:
        for registro_id in ids:
            c.execute(f"SELECT * FROM {table_src} WHERE id=?", (registro_id,))
            row = c.fetchone()
            if not row:
                continue
            c.execute(f"""INSERT INTO {table_dest} (nome, cpf, escritorio, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], office_target, row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11]))
            c.execute(f"DELETE FROM {table_src} WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros movidos com sucesso.", "success")
    except Exception as e:
        flash("Erro ao migrar em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("table", office=office_target))

# -------------------------
# Export CSV / PDF (per office)
# -------------------------
@app.route("/export/csv")
def export_csv():
    office = request.args.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
    except Exception:
        rows = []
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id","nome","cpf","escritorio","tipo_acao","data_fechamento","pendencias","numero_processo","data_protocolo","observacoes","captador","created_at"])
    for r in rows:
        writer.writerow([str(x) for x in r])
    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(mem, as_attachment=True, download_name=f"{office}_export.csv", mimetype="text/csv")

@app.route("/export/pdf")
def export_pdf():
    office = request.args.get("office", "central").replace(" ", "_").lower()
    table = f"office_{office}"
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
    except Exception:
        rows = []
    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    p.setFont("Helvetica-Bold", 12)
    p.drawString(40, y, f"Registros - Escritório {office}")
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
    return send_file(buffer, as_attachment=True, download_name=f"{office}_export.pdf", mimetype="application/pdf")

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
