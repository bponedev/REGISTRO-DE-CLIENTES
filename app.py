from flask import Flask, request, send_file, render_template, redirect, url_for
import sqlite3, csv, io, os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Define o caminho do banco de dados para que funcione em qualquer lugar
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

# Configura o Flask para usar as pastas padrão (templates e static)
app = Flask(__name__, static_folder='static', template_folder='templates')

# REMOVIDO: INDEX_HTML, TABLE_HTML, EXCLUIDOS_HTML

def get_conn():
    conn = sqlite3.connect(DB_PATH) # Usa o DB_PATH corrigido
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Tabela principal de exemplo
    c.execute("""CREATE TABLE IF NOT EXISTS office_Central (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
    )""")
    # Tabela de excluídos
    c.execute("""CREATE TABLE IF NOT EXISTS excluidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio_origem TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT,
        data_exclusao TEXT
    )""")
    conn.commit()
    conn.close()

# Inicializa o banco de dados ao iniciar
with app.app_context():
    init_db()

def get_offices():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'office_%';")
    # Retorna apenas o nome da tabela (ex: office_Central)
    offices = [r['name'] for r in c.fetchall()]
    conn.close()
    return offices

# =========================================================================
# ROTAS PRINCIPAIS
# =========================================================================

@app.route('/')
def index():
    # Retorna o template index.html (NÃO MAIS INDEX_HTML)
    return render_template('index.html')

@app.route('/table')
def table():
    office_name = request.args.get('office', 'Central')
    table_name = f"office_{office_name.replace(' ', '_')}"
    
    conn = get_conn()
    c = conn.cursor()
    
    rows = []
    try:
        c.execute(f"SELECT * FROM {table_name}")
        rows = c.fetchall()
    except sqlite3.OperationalError:
        pass # Tabela não existe

    offices_list = [t.replace('office_', '') for t in get_offices()]

    conn.close()
    # Retorna o template table.html (NÃO MAIS TABLE_HTML)
    return render_template('table.html', rows=rows, offices=offices_list, office=office_name)

@app.route('/excluidos')
def excluidos():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM excluidos ORDER BY data_exclusao DESC")
    excluidos = c.fetchall()
    conn.close()
    # Retorna o template excluidos.html (NÃO MAIS EXCLUIDOS_HTML)
    return render_template('excluidos.html', excluidos=excluidos)


# =========================================================================
# ROTAS DE AÇÃO
# =========================================================================

@app.route('/submit', methods=['POST'])
def submit():
    data = request.form.to_dict()
    office = data.get('escritorio', 'Central').strip()
    table_name = f"office_{office.replace(' ', '_')}"
    
    conn = get_conn()
    c = conn.cursor()
    
    # Garante que a tabela existe antes de inserir
    c.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cpf TEXT, escritorio TEXT, tipo_acao TEXT,
        data_fechamento TEXT, pendencias TEXT, numero_processo TEXT,
        data_protocolo TEXT, observacoes TEXT, captador TEXT, created_at TEXT
    )""")

    cols = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 
            'pendencias', 'numero_processo', 'data_protocolo', 
            'observacoes', 'captador', 'created_at']
    
    values = [data.get(col, '') for col in cols[:-1]]
    values.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S')) # created_at

    placeholders = ', '.join(['?'] * len(cols))
    
    c.execute(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()
    
    return redirect(url_for('table', office=office))

# Exclui UM registro e move para 'excluidos'
@app.route('/delete', methods=['POST'])
def delete_record():
    record_id = request.form.get('id')
    office_name = request.form.get('table')
    table_name = f"office_{office_name.replace(' ', '_')}"

    if not record_id or not office_name:
        return "ID ou Tabela não fornecidos", 400

    conn = get_conn()
    c = conn.cursor()
    
    try:
        # 1. Seleciona o registro a ser movido
        c.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
        row = c.fetchone()

        if row:
            # 2. Insere na tabela 'excluidos'
            row_dict = dict(row)
            cols = [k for k in row_dict.keys() if k != 'id'] + ['escritorio_origem', 'data_exclusao']
            
            # Remove a coluna 'escritorio' e substitui por 'escritorio_origem'
            del row_dict['escritorio'] 
            values = [row_dict.get(k, '') for k in ['nome', 'cpf', 'tipo_acao', 'data_fechamento', 'pendencias', 'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']]
            
            # Adiciona escritorio_origem e data_exclusao
            values.append(office_name) 
            values.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

            placeholders = ', '.join(['?'] * len(cols))
            
            c.execute(f"INSERT INTO excluidos ({', '.join(cols)}) VALUES ({placeholders})", values)
            
            # 3. Deleta da tabela de origem
            c.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
            conn.commit()
            
    except sqlite3.OperationalError as e:
        conn.close()
        return f"Erro ao deletar/mover: {e}", 500
        
    conn.close()
    return redirect(url_for('table', office=office_name))

# Exclui MÚLTIPLOS registros e move para 'excluidos'
@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    # 'ids' virá como lista de strings do script.js
    ids = request.form.getlist('ids') 
    office_name = request.form.get('table')
    table_name = f"office_{office_name.replace(' ', '_')}"

    if not ids or not office_name:
        return "IDs ou Tabela não fornecidos", 400

    conn = get_conn()
    c = conn.cursor()

    try:
        for record_id in ids:
            # 1. Seleciona o registro
            c.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
            row = c.fetchone()

            if row:
                # 2. Insere na tabela 'excluidos'
                row_dict = dict(row)
                cols = [k for k in row_dict.keys() if k != 'id'] + ['escritorio_origem', 'data_exclusao']
                
                # Prepara os valores
                del row_dict['escritorio']
                values = [row_dict.get(k, '') for k in ['nome', 'cpf', 'tipo_acao', 'data_fechamento', 'pendencias', 'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']]
                
                # Adiciona escritorio_origem e data_exclusao
                values.append(office_name) 
                values.append(datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

                placeholders = ', '.join(['?'] * len(cols))
                c.execute(f"INSERT INTO excluidos ({', '.join(cols)}) VALUES ({placeholders})", values)
                
                # 3. Deleta da tabela de origem
                c.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        
        conn.commit()
            
    except sqlite3.OperationalError as e:
        conn.close()
        return f"Erro ao deletar/mover em lote: {e}", 500
        
    conn.close()
    return redirect(url_for('table', office=office_name))

# Restaura UM registro da tabela 'excluidos'
@app.route('/restore', methods=['POST'])
def restore_record():
    record_id = request.form.get('id')
    
    if not record_id:
        return "ID não fornecido", 400

    conn = get_conn()
    c = conn.cursor()
    
    try:
        # 1. Seleciona o registro da lixeira
        c.execute("SELECT * FROM excluidos WHERE id = ?", (record_id,))
        row = c.fetchone()

        if row:
            row_dict = dict(row)
            office_name = row_dict['escritorio_origem']
            table_name = f"office_{office_name.replace(' ', '_')}"
            
            # Garante que a tabela de destino existe antes de inserir
            init_db() 

            # 2. Insere na tabela de origem (usando a coluna 'escritorio' que é necessária)
            cols = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 
                    'pendencias', 'numero_processo', 'data_protocolo', 
                    'observacoes', 'captador', 'created_at']
            
            # Prepara os valores para a tabela de destino
            values = [row_dict.get(k, '') for k in ['nome', 'cpf']]
            values.append(office_name) # escritorio
            values.extend([row_dict.get(k, '') for k in ['tipo_acao', 'data_fechamento', 'pendencias', 'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']])

            placeholders = ', '.join(['?'] * len(cols))
            
            c.execute(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})", values)
            
            # 3. Deleta da tabela 'excluidos'
            c.execute("DELETE FROM excluidos WHERE id = ?", (record_id,))
            conn.commit()
            
    except sqlite3.OperationalError as e:
        conn.close()
        return f"Erro ao restaurar/mover: {e}", 500
        
    conn.close()
    return redirect(url_for('excluidos'))

# Restaura MÚLTIPLOS registros da tabela 'excluidos'
@app.route('/restore_selected', methods=['POST'])
def restore_selected():
    ids = request.form.getlist('ids')
    
    if not ids:
        return "IDs não fornecidos", 400

    conn = get_conn()
    c = conn.cursor()

    try:
        for record_id in ids:
            # 1. Seleciona o registro da lixeira
            c.execute("SELECT * FROM excluidos WHERE id = ?", (record_id,))
            row = c.fetchone()

            if row:
                row_dict = dict(row)
                office_name = row_dict['escritorio_origem']
                table_name = f"office_{office_name.replace(' ', '_')}"
                
                # Garante que a tabela de destino existe antes de inserir
                init_db() 

                # 2. Insere na tabela de origem (usando a coluna 'escritorio' que é necessária)
                cols = ['nome', 'cpf', 'escritorio', 'tipo_acao', 'data_fechamento', 
                        'pendencias', 'numero_processo', 'data_protocolo', 
                        'observacoes', 'captador', 'created_at']
                
                # Prepara os valores para a tabela de destino
                values = [row_dict.get(k, '') for k in ['nome', 'cpf']]
                values.append(office_name) # escritorio
                values.extend([row_dict.get(k, '') for k in ['tipo_acao', 'data_fechamento', 'pendencias', 'numero_processo', 'data_protocolo', 'observacoes', 'captador', 'created_at']])

                placeholders = ', '.join(['?'] * len(cols))
                
                c.execute(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})", values)
                
                # 3. Deleta da tabela 'excluidos'
                c.execute("DELETE FROM excluidos WHERE id = ?", (record_id,))

        conn.commit()
            
    except sqlite3.OperationalError as e:
        conn.close()
        return f"Erro ao restaurar/mover em lote: {e}", 500
        
    conn.close()
    return redirect(url_for('excluidos'))


# =========================================================================
# ROTAS DE EXPORTAÇÃO
# =========================================================================

@app.route('/export/csv')
def export_csv():
    office = request.args.get('office', 'Central')
    conn = get_conn()
    c = conn.cursor()
    
    tables = []
    if office.lower() == 'all':
        tables = get_offices()
    elif office == 'excluidos':
        tables = ['excluidos']
    else:
        tables = [f"office_{office.replace(' ', '_')}"]

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';') # Mantendo o delimitador ';'

    for t in tables:
        writer.writerow([f"Tabela: {t}"]) # Cabeçalho da tabela
        try:
            c.execute(f"SELECT * FROM {t}")
            rows = c.fetchall()
            if rows:
                cols = [d[0] for d in c.description]
                writer.writerow(cols) # Nomes das colunas
                for row in rows:
                    writer.writerow([str(r) for r in row]) # Dados
            else:
                writer.writerow(["Sem registros."])
        except:
            writer.writerow(["Erro ao ler a tabela ou tabela não encontrada."])
        writer.writerow([]) # Linha em branco para separar tabelas

    conn.close()
    buffer.seek(0)
    
    # Envia o arquivo CSV
    return send_file(io.BytesIO(buffer.getvalue().encode('utf-8')), 
                     mimetype='text/csv', 
                     as_attachment=True, 
                     download_name=f'registros_{office}_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv')


@app.route('/export/pdf')
def export_pdf():
    office = request.args.get('office', 'Central')
    conn = get_conn()
    c = conn.cursor()
    
    tables = []
    if office.lower() == 'all':
        tables = get_offices()
    elif office == 'excluidos':
        tables = ['excluidos']
    else:
        tables = [f"office_{office.replace(' ', '_')}"]
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 80

    # Lógica de cabeçalho do PDF (Logo, Título, Data)
    logo_path = os.path.join(app.root_path, 'logo', 'logo.png') # Corrigido para caminho absoluto
    if os.path.exists(logo_path):
        try: p.drawImage(logo_path, 40, y-20, width=60, preserveAspectRatio=True)
        except: pass

    p.setFont("Helvetica-Bold", 14)
    p.drawString(120, y, "Sistema de Registro de Clientes")
    p.setFont("Helvetica", 10)
    p.drawString(120, y-16, f"Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    y -= 40
    
    # Renderização dos dados no PDF
    for t in tables:
        p.setFont("Helvetica-Bold", 12)
        p.drawString(40, y, f"Tabela: {t}"); y -= 16
        try:
            # Pega as colunas para o cabeçalho da tabela no PDF
            cols = [d[0] for d in c.execute(f"PRAGMA table_info({t})")]
            
            # Cabeçalho da tabela (colunas)
            header_y = y
            x_offset = 50
            for col in cols:
                if header_y < 80: p.showPage(); y = height - 80; header_y = y
                p.setFont("Helvetica-Bold", 8)
                p.drawString(x_offset, header_y, col.upper())
                x_offset += 80 # Espaçamento
            y -= 12
            
            # Dados
            for row in c.execute(f"SELECT * FROM {t}"):
                if y < 80: p.showPage(); y = height - 80 # Nova página
                
                p.setFont("Helvetica", 7)
                x_offset = 50
                for data in row:
                    p.drawString(x_offset, y, str(data))
                    x_offset += 80
                y -= 12
                
        except:
            p.setFont("Helvetica", 9)
            p.drawString(40, y, "Erro ao ler a tabela ou tabela não encontrada.")
            y -= 12
        
        y -= 20 # Espaço entre tabelas
        if y < 80: p.showPage(); y = height - 80

    p.save()
    buffer.seek(0)
    
    # Envia o arquivo PDF
    return send_file(buffer, 
                     mimetype='application/pdf', 
                     as_attachment=True, 
                     download_name=f'registros_{office}_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')


if __name__ == '__main__':
    # Apenas para desenvolvimento local
    app.run(debug=True)
