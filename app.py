@app.route("/table")
def table():
    office = request.args.get("office")

    # Caso o usuário não tenha escolhido ainda → Central
    if not office or office.strip() == "":
        office = "Central"

    # Normalizar nomes
    office_clean = office.replace(" ", "_").lower()

    # Tabela correspondente
    table_name = f"office_{office_clean}"

    # Garantir que a tabela existe
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
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

    # Buscar registros
    c.execute(f"SELECT * FROM {table_name} ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    return render_template("table.html", rows=rows, office=office_clean)
