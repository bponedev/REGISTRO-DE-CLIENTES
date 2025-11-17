# /app.py
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
import sqlite3
import os
import io
import csv
import re
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "troque_para_uma_chave_secreta"

# -------------------------
# DB helpers
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = None
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # excluidos table, with escritorio_nome and escritorio_chave
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
    # offices_meta to store mapping office_key <-> display name
    c.execute("""
        CREATE TABLE IF NOT EXISTS offices_meta (
            office_key TEXT PRIMARY KEY,
            display_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def normalize_office_raw(name: str) -> str:
    """
    Option 2 base: replace spaces with underscores; remove invalid chars;
    then convert to uppercase for consistency of office_key.
    """
    if not name:
        return ""
    s = name.strip()
    s = s.replace(" ", "_")
    s_clean = re.sub(r'[^A-Za-z0-9_]', '', s)
    return s_clean.upper()

def create_office_table(office_key: str):
    """
    Ensure table exists and has required schema (add columns if missing).
    office_key is already normalized (UPPER, underscores).
    """
    if not office_key:
        office_key = "CENTRAL"
    table = f"office_{office_key}"
    conn = get_conn()
    c = conn.cursor()
    # Create table if not exists with basic columns
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
    """
    Ensure an existing table has our schema columns (backwards compatibility).
    Adds columns if needed.
    """
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

def list_offices_meta():
    """
    Return list of dicts: [{'key': 'CENTRAL', 'display': 'CENTRAL'}, ...]
    Ensures that 'CENTRAL' exists.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT office_key, display_name FROM offices_meta ORDER BY office_key")
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({"key": r[0], "display": r[1]})
    # ensure CENTRAL exists
    if not any(o["key"] == "CENTRAL" for o in out):
        out.insert(0, {"key": "CENTRAL", "display": "CENTRAL"})
    return out

def register_office_meta(office_key: str, display_name: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO offices_meta (office_key, display_name) VALUES (?,?)", (office_key, display_name))
        conn.commit()
    finally:
        conn.close()

def remove_office_meta(office_key: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM offices_meta WHERE office_key=?", (office_key,))
        conn.commit()
    finally:
        conn.close()

def get_office_display(office_key: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT display_name FROM offices_meta WHERE office_key=?", (office_key,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    # fallback: format key
    return office_key.replace("_", " ").upper()

# initialize DB
init_db()

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    offices = list_offices_meta()
    return render_template("index.html", offices=offices)

# create office via manage page (POST)
@app.route("/create_office", methods=["POST"])
def create_office():
    name = request.form.get("office_new", "").strip()
    if not name:
        flash("Nome inválido.", "error")
        return redirect(url_for("offices_page"))
    key = normalize_office_raw(name)
    display = name.strip().upper()
    # register meta and table
    register_office_meta(key, display)
    create_office_table(key)
    flash(f"Escritório '{display}' criado.", "success")
    return redirect(url_for("offices_page"))

# Submit new client
@app.route("/submit", methods=["POST"])
def submit():
    data = request.form
    nome = data.get("nome", "").strip()
    cpf = data.get("cpf", "").strip()
    escritorio_raw = data.get("escritorio", "CENTRAL").strip()
    office_key = normalize_office_raw(escritorio_raw) or "CENTRAL"
    display_name = escritorio_raw.strip().upper() if escritorio_raw.strip() else office_key.replace("_", " ").upper()

    # register meta if not exists
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

# Table listing (office key or ALL)
@app.route("/table")
def table():
    office_param = request.args.get("office", "CENTRAL").strip()
    office = office_param.upper()
    # special ALL case
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

    rows = []
    total = 0

    conn = get_conn()
    c = conn.cursor()

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

    if office == "ALL":
        # gather all office tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%' ORDER BY name")
        office_tables = [r[0] for r in c.fetchall()]
        all_rows = []
        for t in office_tables:
            try:
                ensure_table_columns(t)
                q = f"SELECT *, '{t}' as _table_source FROM {t}"
                where_parts = []
                params = []
                match_filters(where_parts, params)
                if where_parts:
                    q += " WHERE " + " AND ".join(where_parts)
                q += " ORDER BY id DESC"
                c.execute(q, tuple(params))
                fetched = c.fetchall()
                # annotate with table name
                for fr in fetched:
                    # fr is a tuple; append source table name at the end
                    all_rows.append((t,) + fr)
            except Exception:
                continue
        # sort by created (assume created_at at position -2 maybe) or id; we'll sort by created_at if possible
        # created_at column is at index for each table: after captador, created_at is last column in our schema
        def sort_key(x):
            try:
                # x[1:] corresponds to original row starting id at index 1
                created = x[-2]  # because we prefixed t -> (t, id, nome, ..., created_at, )
                return created or ""
            except:
                return ""
        all_rows.sort(key=sort_key, reverse=True)
        total = len(all_rows)
        # pagination slice
        start = (page - 1) * per_page
        end = start + per_page
        paged = all_rows[start:end]
        # transform to normalized rows expected by template: we will expose as list of tuples where positions correspond:
        rows = []
        for ar in paged:
            tname = ar[0]
            row = ar[1:]  # original table row
            # ensure row has escritorio_nome / escritorio_chave; if not, derive
            # positions: id(0), nome(1), cpf(2), escritorio_nome(3)?, escritorio_chave(4)? etc. We'll map robustly:
            # Build a dict by reading PRAGMA for that table and mapping columns to values
            # For simplicity in template, we'll produce a tuple with fixed indexes:
            # 0 id,1 nome,2 cpf,3 escritorio_nome,4 escritorio_chave,5 tipo_acao,6 data_fechamento,7 pendencias,8 numero_processo,9 data_protocolo,10 observacoes,11 captador,12 created_at
            # We'll attempt to align by length
            vals = list(row)
            # pad to expected length 12 if needed
            while len(vals) < 12:
                vals.append(None)
            # reorder / extract possible escritorio fields if they are present (best-effort)
            # If escritorio_nome exists at index 3 (common), keep
            rows.append(tuple(vals[:12]))
    else:
        office_key = normalize_office_raw(office)
        table = f"office_{office_key}"
        create_office_table(office_key)
        ensure_table_columns(table)
        where_parts = []
        params = []
        match_filters(where_parts, params)
        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)
        # count
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
        q = f"SELECT * FROM {table} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
        try:
            q_params = params + [per_page, offset]
            c.execute(q, tuple(q_params))
            rows = c.fetchall()
        except Exception:
            rows = []
    conn.close()
    total_pages = max(1, (total + per_page -1)//per_page)
    offices = list_offices_meta()
    return render_template("table.html",
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
                           data_ate=data_ate)

# Edit client (form)
@app.route("/edit")
def edit():
    registro_id = request.args.get("id")
    office_raw = request.args.get("office", "CENTRAL")
    office_key = normalize_office_raw(office_raw)
    if not office_key:
        office_key = "CENTRAL"
    table = f"office_{office_key}"
    ensure_table_columns(table)
    conn = get_conn()
    c = conn.cursor()
    row = None
    try:
        c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
        row = c.fetchone()
    except Exception:
        row = None
    conn.close()
    if not row:
        flash("Registro não encontrado.", "error")
        return redirect(url_for("table", office=office_key))
    # Map to dict with keys
    cliente = {
        "id": row[0],
        "nome": row[1],
        "cpf": row[2],
        "escritorio_nome": row[3] if len(row) > 3 else "",
        "escritorio_chave": row[4] if len(row) > 4 else f"office_{office_key}",
        "tipo_acao": row[5] if len(row) > 5 else "",
        "data_fechamento": row[6] if len(row) > 6 else "",
        "pendencias": row[7] if len(row) > 7 else "",
        "numero_processo": row[8] if len(row) > 8 else "",
        "data_protocolo": row[9] if len(row) > 9 else "",
        "observacoes": row[10] if len(row) > 10 else "",
        "captador": row[11] if len(row) > 11 else "",
        "created_at": row[12] if len(row) > 12 else ""
    }
    offices = list_offices_meta()
    return render_template("edit.html", cliente=cliente, office=office_key, offices=offices)

# Update client (save edits)
@app.route("/update", methods=["POST"])
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
        # if changing office (moving)
        if new_office_key != office_key:
            dest_table = create_office_table(new_office_key)
            ensure_table_columns(dest_table)
            register_office_meta(new_office_key, new_display)
            # copy record from source, update escritorio_nome/chave
            c.execute(f"SELECT * FROM {table} WHERE id=?", (registro_id,))
            old = c.fetchone()
            if old:
                created_at = old[11] if len(old) > 11 else datetime.utcnow().isoformat()
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

# Delete individual (move to excluidos)
@app.route("/delete", methods=["POST"])
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
            # attempt to extract escritorio_nome and escritorio_chave from row; fallback to meta
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

# Delete selected (batch)
@app.route("/delete_selected", methods=["POST"])
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
    offices = list_offices_meta()
    return render_template("excluidos.html", rows=rows, offices=offices)

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
            # row: id, nome, cpf, escritorio_nome, escritorio_chave, ...
            escritorio_chave = row[4] if len(row) > 4 and row[4] else f"office_CENTRAL"
            # derive key
            if escritorio_chave.startswith("office_"):
                office_key = escritorio_chave[len("office_"):]
            else:
                office_key = normalize_office_raw(row[3]) if row[3] else "CENTRAL"
            display_name = row[3] if row[3] else get_office_display(office_key)
            # ensure dest table
            table = create_office_table(office_key)
            ensure_table_columns(table)
            c.execute(f"""INSERT INTO {table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], display_name, escritorio_chave, row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12]))
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
            escritorio_chave = row[4] if len(row) > 4 and row[4] else f"office_CENTRAL"
            if escritorio_chave.startswith("office_"):
                office_key = escritorio_chave[len("office_"):]
            else:
                office_key = normalize_office_raw(row[3]) if row[3] else "CENTRAL"
            display_name = row[3] if row[3] else get_office_display(office_key)
            table = create_office_table(office_key)
            ensure_table_columns(table)
            c.execute(f"""INSERT INTO {table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (row[1], row[2], display_name, escritorio_chave, row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12]))
            c.execute("DELETE FROM excluidos WHERE id=?", (registro_id,))
        conn.commit()
        flash("Registros restaurados.", "success")
    except Exception as e:
        flash("Erro ao restaurar em lote: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("excluidos"))

# Migration single (called from inline select change via POST)
@app.route("/migrate", methods=["POST"])
def migrate():
    registro_id = request.form.get("id")
    from_office_raw = request.form.get("office_current", "CENTRAL")
    target_raw = request.form.get("office_target", "")
    if not target_raw:
        return redirect(url_for("table", office=from_office_raw))
    from_key = normalize_office_raw(from_office_raw) or "CENTRAL"
    to_key = normalize_office_raw(target_raw)
    to_display = target_raw.strip().upper() if target_raw.strip() else to_key.replace("_", " ").upper()
    # ensure dest table and meta
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

# Migrate selected (batch)
@app.route("/migrate_selected", methods=["POST"])
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

# Offices management
@app.route("/offices")
def offices_page():
    offices = list_offices_meta()
    return render_template("offices.html", offices=offices)

# Edit office (rename)
@app.route("/edit_office/<office>")
def edit_office(office):
    office_key = normalize_office_raw(office)
    display = get_office_display(office_key)
    return render_template("edit_office.html", office=office_key, display=display)

@app.route("/rename_office", methods=["POST"])
def rename_office():
    office_old = normalize_office_raw(request.form.get("office_old", ""))
    office_new_input = request.form.get("office_new", "").strip()
    if not office_old or not office_new_input:
        flash("Dados insuficientes.", "error")
        return redirect(url_for("offices_page"))
    office_new = normalize_office_raw(office_new_input)
    if not office_new:
        flash("Nome novo inválido.", "error")
        return redirect(url_for("edit_office", office=office_old))
    table_old = f"office_{office_old}"
    table_new = f"office_{office_new}"
    conn = get_conn()
    c = conn.cursor()
    try:
        # check existence
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_old,))
        if not c.fetchone():
            flash("Escritório de origem não encontrado.", "error")
            return redirect(url_for("offices_page"))
        # avoid overwriting existing dest
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_new,))
        if c.fetchone():
            flash("Destino já existe. Considere mesclar manualmente.", "error")
            return redirect(url_for("offices_page"))
        # rename table
        c.execute(f"ALTER TABLE {table_old} RENAME TO {table_new}")
        # update offices_meta
        new_display = office_new_input.strip().upper()
        c.execute("UPDATE offices_meta SET office_key=?, display_name=? WHERE office_key=?", (office_new, new_display, office_old))
        # update excluidos references
        c.execute("UPDATE excluidos SET escritorio_chave = ? WHERE escritorio_chave = ?", (table_new, table_old))
        conn.commit()
        flash("Escritório renomeado com sucesso.", "success")
    except Exception as e:
        conn.rollback()
        flash("Erro ao renomear escritório: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("offices_page"))

# Delete office (with options)
@app.route("/delete_office", methods=["POST"])
def delete_office():
    office_key = normalize_office_raw(request.form.get("office_key", ""))
    action = request.form.get("action")  # 'move' or 'delete'
    target = request.form.get("target")  # if move, target office key
    if not office_key:
        flash("Escritório inválido.", "error")
        return redirect(url_for("offices_page"))
    table = f"office_{office_key}"
    conn = get_conn()
    c = conn.cursor()
    try:
        # check if table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not c.fetchone():
            # still remove meta
            remove_office_meta(office_key)
            flash("Escritório removido.", "success")
            return redirect(url_for("offices_page"))
        # check if empty
        c.execute(f"SELECT COUNT(*) FROM {table}")
        cnt = c.fetchone()[0]
        if cnt == 0 or action == "delete":
            # delete table and meta
            c.execute(f"DROP TABLE IF EXISTS {table}")
            remove_office_meta(office_key)
            conn.commit()
            flash("Escritório excluído.", "success")
            return redirect(url_for("offices_page"))
        elif action == "move" and target:
            target_key = normalize_office_raw(target)
            target_table = create_office_table(target_key)
            ensure_table_columns(target_table)
            # move all rows
            c.execute(f"INSERT INTO {target_table} (nome, cpf, escritorio_nome, escritorio_chave, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at) SELECT nome, cpf, ?, ?, tipo_acao, data_fechamento, pendencias, numero_processo, data_protocolo, observacoes, captador, created_at FROM {table}", (get_office_display(target_key), f"office_{target_key}"))
            c.execute(f"DROP TABLE IF EXISTS {table}")
            remove_office_meta(office_key)
            conn.commit()
            flash("Escritório excluído e registros movidos.", "success")
            return redirect(url_for("offices_page"))
        else:
            flash("Escritório contém registros. Escolha mover ou excluir.", "error")
            return redirect(url_for("offices_page"))
    except Exception as e:
        conn.rollback()
        flash("Erro ao excluir escritório: " + str(e), "error")
    finally:
        conn.close()
    return redirect(url_for("offices_page"))

# Export CSV / PDF
@app.route("/export/csv")
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
