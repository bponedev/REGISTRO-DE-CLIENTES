from flask import Flask, request, redirect, url_for, send_file, render_template, render_template_string
import sqlite3, csv, io, os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- Configuração de Caminhos e App ---
# O Flask agora procurará por templates na pasta 'templates' e assets na 'static'.
# O caminho do banco de dados é ajustado para ser robusto em produção.
DB_FILE = 'database.db'

# Use um caminho absoluto para o banco de dados
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_FILE)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 # Desabilita cache para arquivos estáticos

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Funções de Suporte (Inalteradas, mas robustas com DB_PATH)
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS office_Central (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS excluidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio_origem TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT,
        data_exclusao TEXT
    )""")
    conn.commit()
    conn.close()

def get_table_names(include_excluidos=True):
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    if not include_excluidos:
        query += " AND name != 'excluidos'"
    cur.execute(query)
    tables = [r['name'] for r in cur.fetchall()]
    conn.close()
    return tables

# --- Rotas Principais (Usando render_template) ---

@app.route('/')
def home():
    # Passa as tabelas disponíveis para o menu de seleção
    tables = [t.replace('office_', '') for t in get_table_names(include_excluidos=False)]
    return render_template('index.html', tables=tables)

@app.route('/table')
def table():
    office_name = request.args.get('office', '')
    
    if not office_name:
        # Se não houver escritório especificado, lista todas as tabelas
        tables = [t.replace('office_', '') for t in get_table_names(include_excluidos=False)]
        return render_template('table.html', tables=tables, rows=None, office_name=None)

    # Se houver escritório, busca os registros
    table_name = f"office_{office_name.replace(' ', '_')}"
    conn = get_conn()
    cur = conn.cursor()
    rows = []
    
    try:
        cur.execute(f"SELECT * FROM {table_name}")
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        # Tabela não existe
        pass 
        
    conn.close()
    
    # Retorna o template, passando os dados
    return render_template('table.html', rows=rows, office_name=office_name, tables=None)


@app.route('/excluidos')
def excluidos():
    conn = get_conn()
    cur = conn.cursor()
    rows = []
    
    try:
        cur.execute(f"SELECT * FROM excluidos ORDER BY data_exclusao DESC")
        rows = [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        # Tabela 'excluidos' não existe
        pass
        
    conn.close()
    
    # Retorna o template, passando os dados
    return render_template('excluidos.html', rows=rows)

# --- Rotas de Ação (Submeter, Excluir, Restaurar) ---

@app.route('/submit', methods=['POST'])
def submit():
    data = request.form.to_dict()
    office = data.get('escritorio', 'Central').strip()
    table_name = f"office_{office.replace(' ', '_')}"
    
    conn = get_conn()
    c = conn.cursor()
    
    # Cria a tabela se não existir
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
    )""")
    
    # Prepara os dados para inserção
    cols = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 'pendencias', 
            'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']
    
    values = [
        data.get('nome', ''), data.get('cpf', ''), office, data.get('tipo_acao', ''), 
        data.get('data_fechamento', ''), data.get('pendencias', ''), data.get('numero_processo', ''), 
        data.get('data_protocolo', ''), data.get('observacoes', ''), data.get('captador', ''),
        datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    ]
    
    placeholders = ', '.join(['?'] * len(cols))
    
    c.execute(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()
    
    return redirect(url_for('table', office=office))

@app.route('/delete', methods=['POST'])
def delete_single():
    record_id = request.form.get('id')
    office_name = request.form.get('table').replace('office_', '')
    table_name = f"office_{office_name.replace(' ', '_')}"
    
    if not record_id or not table_name:
        return redirect(url_for('table'))
    
    conn = get_conn()
    c = conn.cursor()
    
    # 1. Busca o registro
    c.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
    row = c.fetchone()
    if row:
        row_dict = dict(row)
        
        # 2. Move para a tabela 'excluidos'
        cols = ['nome', 'cpf', 'escritorio_origem', 'tipo_acao', 'data_fechamento', 'pendencias', 
                'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at', 'data_exclusao']
        
        values = [row_dict.get(c.replace('_origem', ''), '') for c in cols[:-1]] # Mapeia colunas
        values.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S')) # data_exclusao
        
        placeholders = ', '.join(['?'] * len(cols))
        
        c.execute(f"INSERT INTO excluidos ({', '.join(cols)}) VALUES ({placeholders})", values)
        
        # 3. Exclui da tabela original
        c.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        
    conn.close()
    return redirect(url_for('table', office=office_name))

@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    ids_str = request.form.get('ids', '')
    office_name = request.form.get('table').replace('office_', '')
    table_name = f"office_{office_name.replace(' ', '_')}"

    if not ids_str:
        return redirect(url_for('table', office=office_name))
        
    ids = [int(i.strip()) for i in ids_str.split(',') if i.strip().isdigit()]
    
    if not ids:
        return redirect(url_for('table', office=office_name))
        
    conn = get_conn()
    c = conn.cursor()
    
    date_now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    for record_id in ids:
        # 1. Busca o registro
        c.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
        row = c.fetchone()
        
        if row:
            row_dict = dict(row)
            
            # 2. Move para a tabela 'excluidos'
            cols = ['nome', 'cpf', 'escritorio_origem', 'tipo_acao', 'data_fechamento', 'pendencias', 
                    'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at', 'data_exclusao']
            values = [row_dict.get(c.replace('_origem', ''), '') for c in cols[:-1]]
            values.append(date_now)
            placeholders = ', '.join(['?'] * len(cols))
            c.execute(f"INSERT INTO excluidos ({', '.join(cols)}) VALUES ({placeholders})", values)
            
            # 3. Exclui da tabela original
            c.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
            
    conn.commit()
    conn.close()
    return redirect(url_for('table', office=office_name))


@app.route('/restore', methods=['POST'])
def restore_single():
    record_id = request.form.get('id')
    
    if not record_id:
        return redirect(url_for('excluidos'))
        
    conn = get_conn()
    c = conn.cursor()
    
    # 1. Busca o registro na tabela 'excluidos'
    c.execute(f"SELECT * FROM excluidos WHERE id = ?", (record_id,))
    row = c.fetchone()
    
    if row:
        row_dict = dict(row)
        original_office = row_dict['escritorio_origem']
        table_name = f"office_{original_office.replace(' ', '_')}"
        
        # 2. Insere na tabela de origem (sem data_exclusao)
        cols_orig = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 'pendencias', 
                     'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']
        
        values_orig = [
            row_dict['nome'], row_dict['cpf'], original_office, row_dict['tipo_acao'], 
            row_dict['data_fechamento'], row_dict['pendencias'], row_dict['numero_processo'], 
            row_dict['data_protocolo'], row_dict['observacoes'], row_dict['captador'], 
            row_dict['created_at']
        ]
        
        placeholders = ', '.join(['?'] * len(cols_orig))
        
        # Cria a tabela de origem se não existir
        c.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
            data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
            data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
        )""")
        
        c.execute(f"INSERT INTO {table_name} ({', '.join(cols_orig)}) VALUES ({placeholders})", values_orig)
        
        # 3. Exclui da tabela 'excluidos'
        c.execute(f"DELETE FROM excluidos WHERE id = ?", (record_id,))
        conn.commit()
        
    conn.close()
    return redirect(url_for('excluidos'))

@app.route('/restore_selected', methods=['POST'])
def restore_selected():
    ids_str = request.form.get('ids', '')
    
    if not ids_str:
        return redirect(url_for('excluidos'))
        
    ids = [int(i.strip()) for i in ids_str.split(',') if i.strip().isdigit()]
    
    if not ids:
        return redirect(url_for('excluidos'))
        
    conn = get_conn()
    c = conn.cursor()
    
    for record_id in ids:
        # 1. Busca o registro na tabela 'excluidos'
        c.execute(f"SELECT * FROM excluidos WHERE id = ?", (record_id,))
        row = c.fetchone()
        
        if row:
            row_dict = dict(row)
            original_office = row_dict['escritorio_origem']
            table_name = f"office_{original_office.replace(' ', '_')}"
            
            # 2. Insere na tabela de origem (sem data_exclusao)
            cols_orig = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 'pendencias', 
                         'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']
            
            values_orig = [
                row_dict['nome'], row_dict['cpf'], original_office, row_dict['tipo_acao'], 
                row_dict['data_fechamento'], row_dict['pendencias'], row_dict['numero_processo'], 
                row_dict['data_protocolo'], row_dict['observacoes'], row_dict['captador'], 
                row_dict['created_at']
            ]
            placeholders = ', '.join(['?'] * len(cols_orig))
            
            # Cria a tabela de origem se não existir
            c.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
                data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
                data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
            )""")
            
            c.execute(f"INSERT INTO {table_name} ({', '.join(cols_orig)}) VALUES ({placeholders})", values_orig)
            
            # 3. Exclui da tabela 'excluidos'
            c.execute(f"DELETE FROM excluidos WHERE id = ?", (record_id,))
            
    conn.commit()
    conn.close()
    return redirect(url_for('excluidos'))

# --- Rotas de Exportação (CSV e PDF) ---
# Lógica do PDF simplificada para usar reportlab

def generate_pdf_from_rows(c, tables, buffer):
    """Gera o PDF com os dados das tabelas."""
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4; y = height - 80
    
    # Cabeçalho Fixo
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo', 'logo.png') # Ajustado para path absoluto
    if os.path.exists(logo_path):
        try: p.drawImage(logo_path, 40, y-20, width=60, preserveAspectRatio=True)
        except Exception: pass
        
    p.setFont("Helvetica-Bold", 14); p.drawString(120, y, "Sistema de Registro de Clientes")
    p.setFont("Helvetica", 10); p.drawString(120, y-16, f"Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    y -= 40
    
    for t in tables:
        p.setFont("Helvetica-Bold", 12); p.drawString(40, y, f"Tabela: {t}"); y -= 16
        try:
            # Pega as colunas da tabela
            cur_cols = [d[0] for d in c.execute(f"PRAGMA table_info({t})")]
            
            # Formata a string de título
            title_str = " | ".join([col.upper() for col in cur_cols])
            
            # Desenha o cabeçalho das colunas (uma linha)
            if y < 80: p.showPage(); y = height - 80
            p.setFont("Helvetica-Bold", 8)
            p.drawString(40, y, title_str)
            y -= 10
            
            # Desenha os dados
            for row in c.execute(f"SELECT * FROM {t}"):
                if y < 80: p.showPage(); y = height - 80
                p.setFont("Helvetica", 7) # Fonte menor para caber mais
                row_str = " | ".join([str(v) if v is not None else '' for v in row])
                p.drawString(40, y, row_str)
                y -= 10
            
            y -= 16 # Espaço extra entre tabelas
            
        except sqlite3.OperationalError:
            p.setFont("Helvetica-Bold", 10); p.drawString(40, y, f"Erro: Tabela {t} não encontrada ou vazia.")
            y -= 16
            
    p.save()
    
@app.route('/export/pdf')
def export_pdf():
    office = request.args.get('office', 'Central')
    conn = get_conn()
    c = conn.cursor()
    
    if office.lower() == 'all':
        tables = get_table_names(include_excluidos=True)
        download_name = 'todos_registros.pdf'
    else:
        tables = [f"office_{office.replace(' ', '_')}"]
        download_name = f"{office.replace(' ', '_')}_registros.pdf"

    buffer = io.BytesIO()
    generate_pdf_from_rows(c, tables, buffer)
    buffer.seek(0)
    conn.close()

    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=download_name)


@app.route('/export/csv')
def export_csv():
    office = request.args.get('office', 'Central')
    table_name = f"office_{office.replace(' ', '_')}"
    download_name = f"{table_name}_registros.csv"
    
    conn = get_conn()
    c = conn.cursor()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';') # Usando ';' para evitar problemas com vírgulas em textos

    try:
        # Pega os nomes das colunas (cabeçalho)
        c.execute(f"SELECT * FROM {table_name} LIMIT 0")
        col_names = [d[0] for d in c.description]
        writer.writerow(col_names)

        # Pega os dados
        c.execute(f"SELECT * FROM {table_name}")
        writer.writerows(c.fetchall())
        
    except sqlite3.OperationalError:
        writer.writerow(["Erro", "Tabela não encontrada"])

    conn.close()
    buffer.seek(0)
    
    return send_file(io.BytesIO(buffer.getvalue().encode('utf-8')), 
                     mimetype='text/csv', 
                     as_attachment=True, 
                     download_name=download_name)

# --- Inicialização ---

if __name__ == '__main__':
    # Garante que o banco e a tabela Central existam ao iniciar localmente
    init_db() 
    app.run(debug=True)
