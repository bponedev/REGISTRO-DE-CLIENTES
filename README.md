# SistemaRegistroClientes - GitHub + Render Ready

Este repositório está pronto para deploy automático no Render.com.

## Como usar (local)
- Java 11+ e Maven instalados.
- `mvn -B -DskipTests package`
- `java -jar target/SistemaRegistroClientes-0.0.1-SNAPSHOT.jar`
- Abra `http://localhost:8080/`

## Como fazer deploy no Render (deploy automático via GitHub)
1. Crie um repositório no GitHub e envie todos os arquivos deste projeto.
2. No Render.com, clique em **New → Web Service**.
3. Conecte sua conta GitHub e selecione o repositório.
4. Em **Environment**, escolha **Java**.
5. Em **Build command**, use: `mvn -B -DskipTests package`
6. Em **Start command**, use: `java -jar target/SistemaRegistroClientes-0.0.1-SNAPSHOT.jar`
7. Deploy — o Render fará build e ficará disponível em uma URL pública.

## Banco de dados
- O projeto usa **SQLite** (`database.db`) por padrão para testes. Para produção, recomendo migrar para PostgreSQL e atualizar `application.properties`.

