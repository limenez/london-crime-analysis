# =============================================================================
# conexao_bigquery_london_crime.py
# Projeto: Análise de Crimes em Londres — BigQuery + Python
# Objetivo: Conexão com BigQuery, extração, validação e análise dos dados
# =============================================================================

# ── DEPENDÊNCIAS ──────────────────────────────────────────────────────────────
# pip install google-cloud-bigquery pandas pyarrow db-dtypes

import os
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

# =============================================================================
# BLOCO 1 — CONFIGURAÇÃO E AUTENTICAÇÃO
# =============================================================================

# Opção A: autenticação via arquivo de credenciais JSON (Service Account)
CREDENTIALS_PATH = "credentials/service_account.json"   # ajuste o caminho

# Opção B: variável de ambiente (descomente se preferir)
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH

# Identificadores do projeto e dataset
PROJECT_ID  = "seu-projeto-bigquery"          # substitua pelo seu Project ID
DATASET_ID  = "london_crime"
TABLE_ID    = "crimes"
FULL_TABLE  = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

def criar_cliente() -> bigquery.Client:
    """Cria e retorna um cliente autenticado do BigQuery."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
        print(f"[OK] Conexão estabelecida com o projeto: {PROJECT_ID}")
        return client
    except Exception as e:
        print(f"[ERRO] Falha na autenticação: {e}")
        raise


# =============================================================================
# BLOCO 2 — EXPLORAÇÃO DO SCHEMA
# =============================================================================

def explorar_schema(client: bigquery.Client) -> None:
    """Exibe schema, tipos de dados e volume de registros da tabela."""
    print("\n" + "="*60)
    print("EXPLORAÇÃO DO SCHEMA")
    print("="*60)

    table = client.get_table(FULL_TABLE)
    print(f"\nTabela  : {table.full_table_id}")
    print(f"Linhas  : {table.num_rows:,}")
    print(f"Tamanho : {table.num_bytes / 1e6:.2f} MB")
    print(f"\n{'Campo':<35} {'Tipo':<20} {'Modo'}")
    print("-" * 65)
    for field in table.schema:
        print(f"{field.name:<35} {field.field_type:<20} {field.mode}")


# =============================================================================
# BLOCO 3 — QUERIES DE VALIDAÇÃO E QUALIDADE
# =============================================================================

def executar_query(client: bigquery.Client, sql: str, descricao: str) -> pd.DataFrame:
    """Executa uma query SQL e retorna o resultado como DataFrame."""
    print(f"\n[QUERY] {descricao}")
    df = client.query(sql).to_dataframe()
    print(df.to_string(index=False))
    return df


def validar_dados(client: bigquery.Client) -> None:
    """Executa queries de validação: nulos, inconsistências e volume."""
    print("\n" + "="*60)
    print("VALIDAÇÃO DE QUALIDADE DOS DADOS")
    print("="*60)

    # 3.1 — Amostra dos primeiros registros
    executar_query(
        client,
        f"SELECT * FROM `{FULL_TABLE}` LIMIT 10",
        "Amostra — primeiros 10 registros"
    )

    # 3.2 — Contagem total de registros
    executar_query(
        client,
        f"SELECT COUNT(*) AS total_registros FROM `{FULL_TABLE}`",
        "Total de registros"
    )

    # 3.3 — Verificação de valores nulos por coluna
    executar_query(
        client,
        f"""
        SELECT
            COUNTIF(lsoa_code      IS NULL) AS nulos_lsoa_code,
            COUNTIF(borough        IS NULL) AS nulos_borough,
            COUNTIF(major_category IS NULL) AS nulos_major_category,
            COUNTIF(minor_category IS NULL) AS nulos_minor_category,
            COUNTIF(value          IS NULL) AS nulos_value,
            COUNTIF(year           IS NULL) AS nulos_year,
            COUNTIF(month          IS NULL) AS nulos_month
        FROM `{FULL_TABLE}`
        """,
        "Contagem de valores nulos por coluna"
    )

    # 3.4 — Intervalo temporal dos dados
    executar_query(
        client,
        f"""
        SELECT
            MIN(year)  AS ano_inicial,
            MAX(year)  AS ano_final,
            MIN(month) AS mes_minimo,
            MAX(month) AS mes_maximo
        FROM `{FULL_TABLE}`
        """,
        "Intervalo temporal dos dados"
    )

    # 3.5 — Boroughs distintos
    executar_query(
        client,
        f"""
        SELECT
            COUNT(DISTINCT borough) AS total_boroughs
        FROM `{FULL_TABLE}`
        """,
        "Total de boroughs distintos"
    )

    # 3.6 — Categorias de crime
    executar_query(
        client,
        f"""
        SELECT
            major_category,
            COUNT(*) AS registros
        FROM `{FULL_TABLE}`
        GROUP BY major_category
        ORDER BY registros DESC
        """,
        "Categorias principais de crime e volume"
    )


# =============================================================================
# BLOCO 4 — ANÁLISE ORIENTADA À PERGUNTA DE NEGÓCIO
# Pergunta: Quais tipos de crime estão crescendo ou diminuindo ao longo do
#           tempo em Londres, em quais bairros e onde devem ser priorizadas
#           ações de prevenção e alocação de recursos policiais?
# =============================================================================

def extrair_dados_analiticos(client: bigquery.Client) -> dict[str, pd.DataFrame]:
    """
    Extrai conjuntos de dados prontos para responder à pergunta de negócio.
    Retorna um dicionário com DataFrames temáticos.
    """
    print("\n" + "="*60)
    print("EXTRAÇÃO — ANÁLISE DE NEGÓCIO")
    print("="*60)
    resultados = {}

    # 4.1 — Evolução anual por categoria de crime
    resultados["evolucao_anual"] = executar_query(
        client,
        f"""
        SELECT
            year,
            major_category,
            SUM(value) AS total_ocorrencias
        FROM `{FULL_TABLE}`
        GROUP BY year, major_category
        ORDER BY year, total_ocorrencias DESC
        """,
        "Evolução anual por categoria de crime"
    )

    # 4.2 — Ranking de boroughs por total de crimes
    resultados["ranking_boroughs"] = executar_query(
        client,
        f"""
        SELECT
            borough,
            SUM(value) AS total_ocorrencias
        FROM `{FULL_TABLE}`
        GROUP BY borough
        ORDER BY total_ocorrencias DESC
        LIMIT 20
        """,
        "Top 20 boroughs com mais ocorrências"
    )

    # 4.3 — Tendência de crescimento por categoria (comparação primeiro vs último ano)
    resultados["tendencia_categoria"] = executar_query(
        client,
        f"""
        WITH anos AS (
            SELECT MIN(year) AS ano_min, MAX(year) AS ano_max
            FROM `{FULL_TABLE}`
        ),
        inicio AS (
            SELECT major_category, SUM(value) AS crimes_inicio
            FROM `{FULL_TABLE}`, anos
            WHERE year = ano_min
            GROUP BY major_category
        ),
        fim AS (
            SELECT major_category, SUM(value) AS crimes_fim
            FROM `{FULL_TABLE}`, anos
            WHERE year = ano_max
            GROUP BY major_category
        )
        SELECT
            i.major_category,
            i.crimes_inicio,
            f.crimes_fim,
            f.crimes_fim - i.crimes_inicio             AS variacao_absoluta,
            ROUND(
                (f.crimes_fim - i.crimes_inicio) * 100.0
                / NULLIF(i.crimes_inicio, 0), 2
            )                                           AS variacao_pct
        FROM inicio i
        JOIN fim f USING (major_category)
        ORDER BY variacao_pct DESC
        """,
        "Tendência de crescimento/redução por categoria (primeiro vs último ano)"
    )

    # 4.4 — Borough × categoria: hotspots prioritários
    resultados["hotspots"] = executar_query(
        client,
        f"""
        SELECT
            borough,
            major_category,
            SUM(value) AS total_ocorrencias,
            RANK() OVER (
                PARTITION BY major_category
                ORDER BY SUM(value) DESC
            ) AS rank_no_categoria
        FROM `{FULL_TABLE}`
        GROUP BY borough, major_category
        QUALIFY rank_no_categoria <= 5
        ORDER BY major_category, rank_no_categoria
        """,
        "Top 5 boroughs por categoria de crime (hotspots)"
    )

    # 4.5 — Sazonalidade mensal
    resultados["sazonalidade"] = executar_query(
        client,
        f"""
        SELECT
            month,
            major_category,
            AVG(value) AS media_ocorrencias
        FROM `{FULL_TABLE}`
        GROUP BY month, major_category
        ORDER BY month, media_ocorrencias DESC
        """,
        "Sazonalidade mensal por categoria"
    )

    return resultados


# =============================================================================
# BLOCO 5 — EXPORTAÇÃO PARA CSV (insumo para Power BI)
# =============================================================================

def exportar_csvs(resultados: dict[str, pd.DataFrame], pasta: str = "data/ready") -> None:
    """Salva os DataFrames analíticos em CSV para importação no Power BI."""
    os.makedirs(pasta, exist_ok=True)
    for nome, df in resultados.items():
        caminho = os.path.join(pasta, f"{nome}.csv")
        df.to_csv(caminho, index=False, encoding="utf-8-sig")
        print(f"[SALVO] {caminho}  ({len(df)} linhas)")
    print(f"\n[OK] Todos os arquivos exportados para '{pasta}/'")


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    # 1. Autenticação
    client = criar_cliente()

    # 2. Exploração do schema
    explorar_schema(client)

    # 3. Validação de qualidade
    validar_dados(client)

    # 4. Extração analítica
    resultados = extrair_dados_analiticos(client)

    # 5. Exportação para Power BI
    exportar_csvs(resultados)

    print("\n✅ Pipeline concluído com sucesso.")
