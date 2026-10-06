import sqlite3

DB_PATH = "minha_arbitragem.db"

def init_db(db_path: str = DB_PATH) -> None:
    """Inicializa o banco de dados e cria as tabelas padrão."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Tabela de Usuários / Configurações
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nome_print TEXT DEFAULT '',
                preco_litro REAL DEFAULT 6.00,
                consumo_carro REAL DEFAULT 10.00,
                plano TEXT DEFAULT 'free',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de Jogos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                data TEXT NOT NULL,
                hora TEXT NOT NULL,
                local TEXT DEFAULT '',
                mandante TEXT DEFAULT '',
                visitante TEXT DEFAULT '',
                modalidade TEXT NOT NULL,
                funcao TEXT NOT NULL,
                valor REAL DEFAULT 0.0,
                situacao TEXT DEFAULT 'Agendado',
                pago INTEGER DEFAULT 0,
                contato_nome TEXT DEFAULT '',
                contato_telefone TEXT DEFAULT '',
                km_ida_volta REAL DEFAULT 0.0,
                combustivel REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # Tabela de Uso de IA
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mes_ano TEXT NOT NULL,
                leituras_realizadas INTEGER DEFAULT 0,
                UNIQUE(user_id, mes_ano),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("✅ Banco de dados inicializado com sucesso!")
    
import sqlite3
from typing import Optional, Tuple
from datetime import datetime

LIMITS = {
    'free': {'max_jogos_mes': 15, 'max_prints_mes': 3, 'preco_mes': 0.0},
    'pro': {'max_jogos_mes': 999999, 'max_prints_mes': 60, 'preco_mes': 14.90}
}

FUNCOES_POR_MODALIDADE = {
    "Futebol": ["Árbitro", "Assistente 1", "Assistente 2", "4º árbitro"],
    "Futsal": ["1º árbitro", "2º árbitro", "Anotador", "Cronometrista"],
    "Fut7": ["Árbitro", "Assistente"]
}

class MinhaArbitragemApp:
    def __init__(self, db_path: str = "minha_arbitragem.db"):
        self.db_path = db_path

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def calcular_combustivel(km: float, consumo: float, preco_litro: float) -> float:
        if not km or not consumo or consumo <= 0 or not preco_litro:
            return 0.0
        return round((km / consumo) * preco_litro, 2)

    def checar_limite_jogos(self, user_id: int, data_jogo_str: str) -> Tuple[bool, str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT plano FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            plano = row['plano'] if row else 'free'
            limite_jogos = LIMITS[plano]['max_jogos_mes']

            try:
                dt = datetime.strptime(data_jogo_str[:10], "%Y-%m-%d")
                mes_ano = dt.strftime("%Y-%m")
            except ValueError:
                mes_ano = datetime.now().strftime("%Y-%m")

            cursor.execute("""
                SELECT COUNT(*) as total FROM games
                WHERE user_id = ? AND strftime('%Y-%m', data) = ?
            """, (user_id, mes_ano))
            total_mes = cursor.fetchone()['total']

        if total_mes >= limite_jogos:
            return False, f"Limite mensal atingido ({total_mes}/{limite_jogos}) para o Plano {plano.upper()}."
        return True, ""

    def verificar_conflito_horario(self, user_id: int, data: str, hora: str, game_id_ignore: Optional[int] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*) as total FROM games
                WHERE user_id = ? AND data = ? AND hora = ? AND situacao != 'Cancelado'
            """
            params = [user_id, data, hora]
            if game_id_ignore:
                query += " AND id != ?"
                params.append(game_id_ignore)

            cursor.execute(query, params)
            total = cursor.fetchone()['total']
        return total > 0

    def sugerir_ultimo_valor(self, user_id: int, modalidade: str, funcao: str) -> float:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT valor FROM games
                WHERE user_id = ? AND modalidade = ? AND funcao = ? AND valor > 0
                ORDER BY data DESC, id DESC LIMIT 1
            """, (user_id, modalidade, funcao))
            row = cursor.fetchone()
        return row['valor'] if row else 0.0

    def salvar_jogo(self, user_id: int, jogo_data: dict) -> Tuple[bool, str, Optional[int]]:
        game_id = jogo_data.get('id')
        
        if not game_id:
            pode, msg = self.checar_limite_jogos(user_id, jogo_data['data'])
            if not pode:
                return False, msg, None

        km = float(jogo_data.get('km_ida_volta') or 0.0)
        comb = float(jogo_data.get('combustivel') or 0.0)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Cálculo automático de combustível
            if km > 0 and comb == 0.0:
                cursor.execute("SELECT preco_litro, consumo_carro FROM users WHERE id = ?", (user_id,))
                u = cursor.fetchone()
                if u:
                    comb = self.calcular_combustivel(km, u['consumo_carro'], u['preco_litro'])

            if game_id:
                cursor.execute("""
                    UPDATE games SET
                        data=?, hora=?, local=?, mandante=?, visitante=?,
                        modalidade=?, funcao=?, valor=?, situacao=?, pago=?,
                        contato_nome=?, contato_telefone=?, km_ida_volta=?, combustivel=?
                    WHERE id=? AND user_id=?
                """, (
                    jogo_data['data'], jogo_data['hora'], jogo_data.get('local', ''),
                    jogo_data.get('mandante', ''), jogo_data.get('visitante', ''),
                    jogo_data['modalidade'], jogo_data['funcao'], float(jogo_data.get('valor', 0.0)),
                    jogo_data.get('situacao', 'Agendado'), 1 if jogo_data.get('pago') else 0,
                    jogo_data.get('contato_nome', ''), jogo_data.get('contato_telefone', ''),
                    km, comb, game_id, user_id
                ))
                msg = "Jogo atualizado com sucesso!"
            else:
                cursor.execute("""
                    INSERT INTO games (
                        user_id, data, hora, local, mandante, visitante,
                        modalidade, funcao, valor, situacao, pago,
                        contato_nome, contato_telefone, km_ida_volta, combustivel
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, jogo_data['data'], jogo_data['hora'], jogo_data.get('local', ''),
                    jogo_data.get('mandante', ''), jogo_data.get('visitante', ''),
                    jogo_data['modalidade'], jogo_data['funcao'], float(jogo_data.get('valor', 0.0)),
                    jogo_data.get('situacao', 'Agendado'), 1 if jogo_data.get('pago') else 0,
                    jogo_data.get('contato_nome', ''), jogo_data.get('contato_telefone', ''),
                    km, comb
                ))
                game_id = cursor.lastrowid
                msg = "Jogo cadastrado com sucesso!"
                
            conn.commit()
        return True, msg, game_id

    def obter_resumo_financeiro(self, user_id: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    SUM(CASE WHEN pago = 1 AND situacao != 'Cancelado' THEN valor ELSE 0 END) as recebido,
                    SUM(CASE WHEN pago = 0 AND situacao = 'Realizado' THEN valor ELSE 0 END) as a_receber,
                    SUM(CASE WHEN situacao = 'Agendado' THEN valor ELSE 0 END) as previsto,
                    SUM(CASE WHEN situacao = 'Realizado' THEN combustivel ELSE 0 END) as combustivel_total
                FROM games WHERE user_id = ?
            """, (user_id,))
            quadros = dict(cursor.fetchone())

            cursor.execute("""
                SELECT
                    strftime('%Y-%m', data) as mes,
                    SUM(valor) as total,
                    SUM(CASE WHEN pago = 1 THEN valor ELSE 0 END) as recebido,
                    SUM(CASE WHEN pago = 0 THEN valor ELSE 0 END) as falta,
                    SUM(km_ida_volta) as km,
                    SUM(combustivel) as combustivel,
                    (SUM(valor) - SUM(combustivel)) as liquido
                FROM games
                WHERE user_id = ? AND situacao != 'Cancelado'
                GROUP BY strftime('%Y-%m', data) ORDER BY mes DESC
            """, (user_id,))
            por_mes = [dict(r) for r in cursor.fetchall()]

            cursor.execute("""
                SELECT
                    modalidade,
                    SUM(valor) as total,
                    SUM(CASE WHEN pago = 1 THEN valor ELSE 0 END) as recebido,
                    SUM(CASE WHEN pago = 0 THEN valor ELSE 0 END) as falta,
                    SUM(km_ida_volta) as km,
                    SUM(combustivel) as combustivel,
                    (SUM(valor) - SUM(combustivel)) as liquido
                FROM games
                WHERE user_id = ? AND situacao != 'Cancelado'
                GROUP BY modalidade
            """, (user_id,))
            por_modalidade = [dict(r) for r in cursor.fetchall()]

        return {
            'recebido': quadros['recebido'] or 0.0,
            'a_receber': quadros['a_receber'] or 0.0,
            'previsto': quadros['previsto'] or 0.0,
            'combustivel': quadros['combustivel_total'] or 0.0,
            'por_mes': por_mes,
            'por_modalidade': por_modalidade
        }
        
import json
import os
from typing import Dict, Any, Optional

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

SYSTEM_PROMPT = """
Você é um assistente especializado em ler prints de escalas de arbitragem no Brasil.
Analise a imagem e extraia os dados do jogo em que o árbitro com o nome "{nome_usuario}" está escalado.

Regras:
1. modalidade: "Futebol", "Futsal" ou "Fut7".
2. funcao conforme a modalidade (ex: Árbitro, Assistente 1, 1º árbitro, Anotador).
3. data: Formato YYYY-MM-DD.
4. hora: Formato HH:MM.
5. valor: Valor numérico em Reais (R$).
6. Se não estiver visível, deixe em branco. NUNCA invente informações.

Responda ESTRITAMENTE em formato JSON.
"""

def extrair_jogo_de_print(image_bytes: bytes, nome_usuario: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    api_key = api_key or os.environ.get("GEMINI_API_KEY")

    if not api_key or not GEMINI_AVAILABLE:
        # Mock para testes
        return {
            "data": "2026-10-15",
            "hora": "15:00",
            "local": "Ginásio Municipal",
            "mandante": "União FC",
            "visitante": "Atlético Cláudio",
            "modalidade": "Futsal",
            "funcao": "1º árbitro",
            "valor": 180.0,
            "contato_nome": "Carlos Escalador",
            "contato_telefone": "11988887777"
        }

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = SYSTEM_PROMPT.format(nome_usuario=nome_usuario or "Árbitro")

    image_part = {"mime_type": "image/png", "data": image_bytes}
    response = model.generate_content([prompt, image_part])

    text = response.text.strip()
    
    # Tratamento para limpar formatação de código markdown
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("Erro ao decodificar JSON da IA:", text)
        return {}
    
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from database import init_db
from minha_arbitragem import MinhaArbitragemApp, FUNCOES_POR_MODALIDADE
# from gemini_vision import extrair_jogo_de_print # Descomente quando for usar a IA

# Configuração da página
st.set_page_config(page_title="Minha Arbitragem", page_icon="⚽", layout="centered")

# Estilo visual: CSS personalizado preenchido
st.markdown("""
<style>
    .card-receber { 
        background-color: #0B132B; color: white; padding: 15px; 
        border-radius: 8px; border-left: 6px solid #FACC15; margin-bottom: 15px; 
    }
    .card-pago { 
        background-color: #0B132B; color: white; padding: 15px; 
        border-radius: 8px; border-left: 6px solid #2ECC71; margin-bottom: 15px; 
    }
    .conflito-aviso { color: #E74C3C; font-weight: bold; margin-bottom: 5px;}
</style>
""", unsafe_allow_html=True)

# Inicializa o app e o banco
init_db()
app = MinhaArbitragemApp()

# Sessão do usuário
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = 1
if 'nome_usuario' not in st.session_state:
    st.session_state['nome_usuario'] = "Árbitro Principal"

st.title("⚽ MINHA ARBITRAGEM")

menu = st.tabs(["📋 Minha Escala", "➕ Novo Jogo", "💰 Pagamentos", "⚙️ Configurações"])

# --- TAB 1: ESCALA ---
with menu[0]:
    st.subheader("📋 Minha Escala")
    filtro = st.radio("Filtro:", ["Todos", "A receber", "Pagos"], horizontal=True)

    with sqlite3.connect("minha_arbitragem.db") as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        q = "SELECT * FROM games WHERE user_id = ? "
        if filtro == "A receber": q += "AND pago = 0 AND situacao != 'Cancelado' "
        elif filtro == "Pagos": q += "AND pago = 1 "
        q += "ORDER BY data ASC, hora ASC"
        
        c.execute(q, [st.session_state['user_id']])
        jogos = c.fetchall()

    if not jogos:
        st.info("Nenhum jogo encontrado para este filtro.")

    for j in jogos:
        conflito = app.verificar_conflito_horario(st.session_state['user_id'], j['data'], j['hora'], j['id'])
        card_class = "card-pago" if j['pago'] else "card-receber"

        html_card = f"""
        <div class="{card_class}">
            {f'<div class="conflito-aviso">⚠️ CONFLITO DE HORÁRIO DETECTADO!</div>' if conflito else ''}
            <div style="display: flex; justify-content: space-between;">
                <strong>{j['modalidade']} - {j['funcao']}</strong>
                <strong>R$ {j['valor']:.2f}</strong>
            </div>
            <div style="margin-top: 5px; font-size: 1.1em;">
                <strong>{j['mandante'] or 'A definir'} x {j['visitante'] or 'A definir'}</strong>
            </div>
            <div style="margin-top: 8px; font-size: 0.9em; opacity: 0.8;">
                📅 {datetime.strptime(j['data'], '%Y-%m-%d').strftime('%d/%m/%Y')} às {j['hora']} | 📍 {j['local'] or 'N/I'}
            </div>
        </div>
        """
        st.markdown(html_card, unsafe_allow_html=True)

# --- TAB 2: NOVO JOGO ---
with menu[1]:
    st.subheader("➕ Cadastrar / Editar Jogo")
    with st.form("form_jogo", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            modalidade = st.selectbox("Modalidade", ["Futebol", "Futsal", "Fut7"])
            data = st.date_input("Data", datetime.now())
            mandante = st.text_input("Mandante")
            valor = st.number_input("Valor (R$)", value=0.0, step=10.0)
            situacao = st.selectbox("Situação", ["Agendado", "Realizado", "Cancelado"])
        
        with col2:
            funcao = st.selectbox("Função", FUNCOES_POR_MODALIDADE[modalidade])
            hora = st.time_input("Hora", datetime.now().time())
            visitante = st.text_input("Visitante")
            local = st.text_input("Local")
            km = st.number_input("KM (Ida/Volta)", value=0.0)

        pago = st.checkbox("Pagamento já foi recebido?")

        if st.form_submit_button("💾 Salvar Jogo"):
            j_dict = {
                'data': data.strftime("%Y-%m-%d"), 'hora': hora.strftime("%H:%M"),
                'local': local, 'mandante': mandante, 'visitante': visitante,
                'modalidade': modalidade, 'funcao': funcao, 'valor': valor,
                'situacao': situacao, 'pago': pago, 'km_ida_volta': km
            }
            ok, msg, _ = app.salvar_jogo(st.session_state['user_id'], j_dict)
            if ok:
                st.success(msg)
                # Atualiza a página automaticamente para ver o novo jogo
                st.rerun()
            else: 
                st.error(msg)

# --- TAB 3: PAGAMENTOS ---
with menu[2]:
    st.subheader("💰 Resumo Financeiro")
    resumo = app.obter_resumo_financeiro(st.session_state['user_id'])

    col1, col2 = st.columns(2)
    col1.metric("A Receber", f"R$ {resumo['a_receber']:.2f}")
    col2.metric("Recebido", f"R$ {resumo['recebido']:.2f}")
    
    col3, col4 = st.columns(2)
    col3.metric("Previsto", f"R$ {resumo['previsto']:.2f}")
    col4.metric("Combustível (Gasto)", f"R$ {resumo['combustivel']:.2f}")

    if resumo['por_mes']:
        st.markdown("### 📅 Resumo por Mês")
        df_mes = pd.DataFrame(resumo['por_mes'])
        st.dataframe(df_mes, use_container_width=True, hide_index=True)

# --- TAB 4: CONFIGURAÇÕES (Placeholder) ---
with menu[3]:
    st.subheader("⚙️ Configurações de Perfil")
    st.info("Aqui você poderá alterar seu preço do combustível, plano e e-mail no futuro.")
    