import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google import genai
import json
import pymssql
import io

# ==========================================
# 1. CONFIGURACIÓN INICIAL DE LA APP
# ==========================================
st.set_page_config(
    page_title="RRHH Green Gold - Vacaciones",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CLAVE DE LA API PARA ANÁLISIS AI
API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY)

# ESTRUCTURA DE ICONO Y TITULO
col_logo, col_titulo = st.columns([1, 8])
with col_logo:
    st.image("GREEN GOLD.png", width=80)
with col_titulo:
    st.title("Dashboard RRHH Green Gold Organic")


# --- FUNCIÓN PARA GENERAR EL HTML DE LAS CARDS ---
def create_card(icon_class, title, value, color="#2F9946"):
    """
    Genera el HTML de la tarjeta KPI con soporte para hover animado y sombras brillantes.
    """
    return f"""
    <div class="metric-card" style="--card-color: {color};">
        <div class="metric-icon">
            <i class="fa-solid {icon_class}"></i>
        </div>
        <div class="metric-content">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
        </div>
    </div>
    """

# --- 2. CARGA DE DATOS / CONEXION SQL (CON CACHE) ---
@st.cache_data(ttl=600)
def carga_datos_rrhh():
    server = st.secrets["DB_SERVER"]
    user = st.secrets["DB_USER"]
    password = st.secrets["DB_PASSWORD"]
    database = st.secrets["DB_NAME"]

    dict_rrhh = {
        "vacaciones": pd.DataFrame(), 
        "prestamos": pd.DataFrame(),
        "horas_extras": pd.DataFrame()
    }

    meses_espanol = {
        1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
    }

    try:
        conn = pymssql.connect(server, user, password, database)

        # --- CONSULTA VACACIONES ---
        query_vac = """
        SELECT 
            v.id_vacacion,
            v.folio_registro,
            v.fecha_registro,
            v.hora_registro,
            u.nombre As Ubicacion,
            (e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno) As Empleado,
            v.fecha_inicio,
            v.fecha_fin,
            v.dias_vacacion,
            v.fecha_incorporacion,
            v.observaciones,
            (ue.nombre + ' ' + ue.apellido_paterno + ' ' + ue.apellido_materno) As Usuario,
            et.Estatus,
            v.MotivoVacaciones As Motivo,
            e.vacaciones As Dias_disponibles
        FROM VACACIONES v
        INNER JOIN UBICACION u ON v.id_ubicacion = u.id_ubicacion
        INNER JOIN EMPLEADO e ON v.id_empleado = e.id_empleado
        INNER JOIN USUARIO us ON v.id_usuario = us.id_usuario
        INNER JOIN EMPLEADO ue ON us.id_empleado = ue.id_empleado
        LEFT JOIN Estatus et ON v.ID_Estatus = et.ID_Estatus
        """
        df_vac = pd.read_sql(query_vac, conn)
        df_vac.columns = [col.lower().strip() for col in df_vac.columns]
        # Formatear las fechas
        df_vac['fecha_inicio'] = pd.to_datetime(df_vac['fecha_inicio'], format='mixed', errors='coerce')
        
        df_vac['fecha_registro'] = pd.to_datetime(df_vac['fecha_registro'], format='mixed', errors='coerce')
        df_vac['fecha_fin'] = pd.to_datetime(df_vac['fecha_fin'], format='mixed', errors='coerce')
        df_vac['fecha_incorporacion'] = pd.to_datetime(df_vac['fecha_incorporacion'], format='mixed', errors='coerce')       

        # Limpieza de datos numericos
        df_vac['dias_vacacion'] = pd.to_numeric(df_vac['dias_vacacion'], errors='coerce').fillna(0).astype(int)

        df_vac = df_vac.dropna(subset=['fecha_inicio']) 

        # Agregar dimensiones temporales clave para filtros
        df_vac['año'] = df_vac['fecha_inicio'].dt.year
        df_vac['mes_sort'] = df_vac['fecha_inicio'].dt.to_period('M')
        df_vac['mes_nombre'] = df_vac['fecha_inicio'].dt.month.map(meses_espanol) + '-' + df_vac['fecha_inicio'].dt.strftime('%y')

        dict_rrhh["vacaciones"] = df_vac


        # --- CONSULTA PRESTAMOS ---
        query_pres = """
         SELECT 
            p.id_prestamo,
            p.fecha_registro,
            p.fecha_inicio,
            p.fecha_entrega,
            p.hora_registro,
            u.nombre As Ubicacion,
            (e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno) As Empleado,
            p.cantidad_autorizada,
            p.descuento_semanal,
            p.fecha_fin,
            p.observaciones,
            p.motivo,
            (eu.nombre + ' ' + eu.apellido_paterno + ' ' + eu.apellido_materno) As Usuario,
            et.Estatus
        FROM PRESTAMO p
        LEFT JOIN UBICACION u ON p.id_ubicacion = u.id_ubicacion
        LEFT JOIN EMPLEADO e ON p.id_empleado = e.id_empleado
        LEFT JOIN USUARIO us ON p.id_usuario = us.id_usuario
        LEFT JOIN EMPLEADO eu ON us.id_empleado = eu.id_empleado
        LEFT JOIN Estatus et ON p.ID_Estatus = et.ID_Estatus
        """

        df_pres = pd.read_sql(query_pres, conn)
        df_pres.columns = [col.lower().strip() for col in df_pres.columns]

        # Limpieza estricta de espacios en Ubicación
        df_pres['ubicacion'] = df_pres['ubicacion'].astype(str).str.strip()

        # Rescatamos la fecha disponible de cualquiera de los 3 campos de fecha
        df_pres['fecha_registro'] = pd.to_datetime(df_pres['fecha_registro'], format='mixed', errors='coerce')
        df_pres['fecha_inicio'] = pd.to_datetime(df_pres['fecha_inicio'], format='mixed', errors='coerce')
        df_pres['fecha_entrega'] = pd.to_datetime(df_pres['fecha_entrega'], format='mixed', errors='coerce')

        # Si fecha_registro está vacía, toma fecha_inicio; si no, fecha_entrega
        df_pres['fecha'] = df_pres['fecha_registro'].fillna(df_pres['fecha_inicio']).fillna(df_pres['fecha_entrega'])

        df_pres['cantidad_autorizada'] = pd.to_numeric(df_pres['cantidad_autorizada'], errors='coerce').fillna(0)
        df_pres['descuento_semanal'] = pd.to_numeric(df_pres['descuento_semanal'], errors='coerce').fillna(0)

        # Solo descartamos si de verdad NO hay ninguna fecha en los 3 campos
        df_pres = df_pres.dropna(subset=['fecha'])
        df_pres['año'] = df_pres['fecha'].dt.year
        df_pres['mes_sort'] = df_pres['fecha'].dt.to_period('M')
        df_pres['mes_nombre'] = df_pres['fecha'].dt.month.map(meses_espanol) + '-' + df_pres['fecha'].dt.strftime('%y')

        dict_rrhh["prestamos"] = df_pres

        
        # --- CONSULTA HORAS EXTRAS ---
        query_he = """
        SELECT
            he.id_horaExtra,
            he.folio_registro,
            he.fecha_registro,
            he.hora_registro,
            ub.nombre As Ubicacion,
            e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno As Empleado,
            r.nombre + ' ' + r.apellido_paterno + ' ' + r.apellido_materno As Responsable,
            he.fecha_compensacion,
            he.costo_horaExtra,
            he.costo_horaDoble,
            he.horas_porPagar,
            he.costo_horaTriple,
            he.hora_triple,
            he.total_horaDoble,
            he.total_horaTriple,
            total_aPagar,
            he.motivo_hraExtra As Motivo,
            he.observaciones,
            eu.nombre + ' ' + eu.apellido_paterno + ' ' + eu.apellido_materno As Usuario,
            et.Estatus,
            he.hora_doble
        FROM HORAS_EXTRAS he
        INNER JOIN EMPLEADO e ON he.id_empleado = e.id_empleado
        INNER JOIN UBICACION ub ON e.id_ubicacion = ub.id_ubicacion
        INNER JOIN EMPLEADO r ON he.id_responsable = r.id_empleado
        LEFT JOIN USUARIO u ON he.id_usuario = u.id_usuario
        LEFT JOIN EMPLEADO eu ON u.id_empleado = eu.id_empleado
        LEFT JOIN Estatus et ON he.ID_Estatus = et.ID_Estatus
        """

        df_he = pd.read_sql(query_he, conn)
        df_he.columns = [col.lower().strip() for col in df_he.columns]
        df_he['ubicacion'] = df_he['ubicacion'].astype(str).str.strip()
        df_he['fecha_registro'] = pd.to_datetime(df_he['fecha_registro'], format='mixed', errors='coerce')
        df_he = df_he.dropna(subset=['fecha_registro'])

        # Numéricos
        df_he['total_apagar'] = pd.to_numeric(df_he['total_apagar'], errors='coerce').fillna(0)
        df_he['hora_doble'] = pd.to_numeric(df_he['hora_doble'], errors='coerce').fillna(0)
        df_he['hora_triple'] = pd.to_numeric(df_he['hora_triple'], errors='coerce').fillna(0)
        df_he['total_horas'] = df_he['hora_doble'] + df_he['hora_triple']

        df_he['año'] = df_he['fecha_registro'].dt.year
        df_he['mes_sort'] = df_he['fecha_registro'].dt.to_period('M')
        df_he['mes_nombre'] = df_he['fecha_registro'].dt.month.map(meses_espanol) + '-' + df_he['fecha_registro'].dt.strftime('%y')

        dict_rrhh["horas_extras"] = df_he

        # --- CONSULTA INCAPACIDAD ---
        query_inc = """
        SELECT 
            i.id_incapacidad,
            i.folio_registro,
            i.fecha_registro,
            i.hora_registro,
            u.nombre As Ubicacion,
            e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno As Empleado,
            i.institucion,
            i.otra_institucion,
            i.pago_jornada,
            i.horas_pagadas,
            i.descripcion,
            i.observaciones,
            i.goce_sueldo,
            eu.nombre + ' ' + eu.apellido_paterno + ' ' + eu.apellido_materno As Usuario
        FROM INCAPACIDAD i
        INNER JOIN UBICACION u ON i.id_ubicacion = u.id_ubicacion
        INNER JOIN EMPLEADO e ON i.id_empleado = e.id_empleado
        LEFT JOIN USUARIO us ON i.id_usuario = us.id_usuario
        LEFT JOIN EMPLEADO eu ON us.id_empleado = eu.id_empleado
        """

        df_inc = pd.read_sql(query_inc, conn)
        df_inc.columns = [col.lower().strip() for col in df_inc.columns]
        
        df_inc['ubicacion'] = df_inc['ubicacion'].astype(str).str.strip()
        df_inc['fecha_registro'] = pd.to_datetime(df_inc['fecha_registro'], format='mixed', errors='coerce')
        df_inc = df_inc.dropna(subset=['fecha_registro'])

        # Limpieza de valores numéricos
        df_inc['horas_pagadas'] = pd.to_numeric(df_inc['horas_pagadas'], errors='coerce').fillna(0)
        
        # Unificamos institución (si eligió otra, toma otra_institucion)
        df_inc['institucion_final'] = df_inc['institucion'].fillna(df_inc['otra_institucion']).fillna('No Especificada')

        df_inc['año'] = df_inc['fecha_registro'].dt.year
        df_inc['mes_sort'] = df_inc['fecha_registro'].dt.to_period('M')
        df_inc['mes_nombre'] = df_inc['fecha_registro'].dt.month.map(meses_espanol) + '-' + df_inc['fecha_registro'].dt.strftime('%y')

        dict_rrhh["incapacidades"] = df_inc

        query_per = """
        SELECT 
            p.id_permiso,
            p.folio,
            p.fecha_registro,
            p.hora_registro,
            u.nombre AS Ubicacion,
            e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno As Empleado,
            e.salario,
            p.tipo_permiso,
            p.horas,
            p.descuento_dias,
            p.dias_descontados,
            p.fecha_inicio,
            p.fecha_fin,
            p.goce_sueldo,
            p.motivo_permiso As Motivo,
            p.observaciones,
            eu.nombre + ' ' + eu.apellido_paterno + ' ' + eu.apellido_materno As Usuario,
            et.Estatus
        FROM PERMISO p
        INNER JOIN UBICACION u ON p.id_ubicacion = u.id_ubicacion
        INNER JOIN EMPLEADO e ON p.id_empleado = e.id_empleado
        INNER JOIN USUARIO us ON p.id_usuario = us.id_usuario
        INNER JOIN EMPLEADO eu ON us.id_empleado = eu.id_empleado
        INNER JOIN Estatus et ON p.ID_Estatus = et.ID_Estatus
        """
        df_per = pd.read_sql(query_per, conn)
        df_per.columns = [col.lower().strip() for col in df_per.columns]

        df_per['ubicacion'] = df_per['ubicacion'].astype(str).str.strip()
        df_per['fecha_inicio'] = pd.to_datetime(df_per['fecha_inicio'], format='mixed', errors='coerce')
        df_per['fecha_registro'] = pd.to_datetime(df_per['fecha_registro'], format='mixed', errors='coerce')
        
        df_per['fecha'] = df_per['fecha_inicio'].fillna(df_per['fecha_registro'])
        df_per = df_per.dropna(subset=['fecha'])

        # Numéricos
        df_per['salario'] = pd.to_numeric(df_per['salario'], errors='coerce').fillna(0)
        df_per['horas'] = pd.to_numeric(df_per['horas'], errors='coerce').fillna(0)
        df_per['dias_descontados'] = pd.to_numeric(df_per['dias_descontados'], errors='coerce').fillna(0)

        # 🟢 CÁLCULO MONETARIO DEL DESCUENTO
        # Asumiendo que 'salario' es el Salario Diario (si es mensual, cambia por df_per['salario'] / 30)
        df_per['salario_diario'] = df_per['salario'] 
        df_per['costo_hora'] = df_per['salario_diario'] / 8.0

        # Si el permiso fue sin goce de sueldo, calculamos el descuento monetario
        es_sin_goce = ~df_per['goce_sueldo'].astype(str).str.upper().str.strip().isin(['SI', '1', 'TRUE', 'S'])
        
        df_per['monto_descontado'] = 0.0
        # Descuento por días
        df_per.loc[es_sin_goce, 'monto_descontado'] = df_per['dias_descontados'] * df_per['salario_diario']
        # Si dias_descontados es 0 pero hay horas registradas, descontamos por hora
        monto_horas = df_per['horas'] * df_per['costo_hora']
        df_per.loc[es_sin_goce & (df_per['dias_descontados'] == 0), 'monto_descontado'] = monto_horas

        df_per['año'] = df_per['fecha'].dt.year
        df_per['mes_sort'] = df_per['fecha'].dt.to_period('M')
        df_per['mes_nombre'] = df_per['fecha'].dt.month.map(meses_espanol) + '-' + df_per['fecha'].dt.strftime('%y')

        dict_rrhh["permisos"] = df_per


        # --- CONSULTA SANCIONES ---
        query_san = """
        SELECT 
            s.id_sancion,
            s.folio,
            s.fecha_registro,
            s.hora_registro,
            u.nombre As Ubicacion,
            e.nombre + ' ' + e.apellido_paterno + ' ' + e.apellido_materno As Empleado,
            e.salario,
            s.tipo_sancion,
            s.consecuencia,
            s.descuento_dias,
            s.dias_descontados,
            s.fecha_inicio,
            s.fecha_fin,
            s.goce_sueldo,
            s.motivo,
            s.observacion As Observaciones,
            eu.nombre + ' ' + eu.apellido_paterno + ' ' + eu.apellido_materno As Usuario
        FROM SANCION s
        INNER JOIN UBICACION u ON s.id_ubicacion = u.id_ubicacion
        INNER JOIN EMPLEADO e ON s.id_empleado = e.id_empleado
        INNER JOIN USUARIO us ON s.id_usuario = us.id_usuario
        INNER JOIN EMPLEADO eu ON us.id_empleado = eu.id_empleado
        INNER JOIN Estatus et ON s.ID_Estatus = et.ID_Estatus
        """

        df_san = pd.read_sql(query_san, conn)
        df_san.columns = [col.lower().strip() for col in df_san.columns]

        df_san['ubicacion'] = df_san['ubicacion'].astype(str).str.strip()
        df_san['fecha_inicio'] = pd.to_datetime(df_san['fecha_inicio'], format='mixed', errors='coerce')
        df_san['fecha_registro'] = pd.to_datetime(df_san['fecha_registro'], format='mixed', errors='coerce')
        
        df_san['fecha'] = df_san['fecha_inicio'].fillna(df_san['fecha_registro'])
        df_san = df_san.dropna(subset=['fecha'])

        # Numéricos y Cálculos Monetarios
        df_san['salario'] = pd.to_numeric(df_san['salario'], errors='coerce').fillna(0)
        df_san['dias_descontados'] = pd.to_numeric(df_san['dias_descontados'], errors='coerce').fillna(0)
        
        # Descuento monetario derivado de suspensiones / días descontados
        df_san['monto_descontado'] = df_san['dias_descontados'] * df_san['salario']

        df_san['año'] = df_san['fecha'].dt.year
        df_san['mes_sort'] = df_san['fecha'].dt.to_period('M')
        df_san['mes_nombre'] = df_san['fecha'].dt.month.map(meses_espanol) + '-' + df_san['fecha'].dt.strftime('%y')

        dict_rrhh["sanciones"] = df_san

        conn.close()
        return dict_rrhh

    except Exception as connection_error:
        st.error(f"⚠️ Error al conectar con SQL Server: {connection_error}")
        return dict_rrhh

dict_rrhh = carga_datos_rrhh()

def analizar_motivos_vacaciones_ia(df_filtrado):
    if df_filtrado.empty:
        return None
    
    reportes = ""
    df_limpio = df_filtrado[['id_vacacion','motivo','observaciones']].dropna(subset=['motivo']).tail(40)

    for idx, row in df_limpio.iterrows():
        obs = row['observaciones'] if row['observaciones'] else "Sin observaciones"
        reportes += f"ID:{row['id_vacacion']} - Mtv: {row['motivo']} (Obs: {obs}) | "

    prompt = f"""
    Eres un analista experto en Capital Humano. Analiza las siguientes razones de solicitud de vacaciones de los empleados y clasificalas estrictamente en 5 categorias.

    Datos a evaluar: {reportes}

    Responde UNICAMENTE un formato JSON estricto con esta estructura exacta, sin textos adicionales ni marcas:
    {{
        "Categorias": {{"Descanso y Viajes": 12, "Salud y Bienestar": 4, "Tramites Personales": 2, "Eventos Familiares": 5, "Otros": 1}},
        "Asignaciones": {{"Descanso y Viajes": [72, 75], "Salud y Bienestar": [73], "Tramites Personales": [74], "Eventos Familiares": [], "Otros": []}}
    }}
    Donde los numeros dentro de los arreglos de 'Asignaciones' deben ser los 'ID' numericos exactos de las vacaciones que te envie.
    """

    try: 
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )
        texto_limpio = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error en el motor analitico de IA: {e}")
        return None



def analizar_motivos_prestamos_ia(df_filtrado):
    if df_filtrado.empty:
        return None

    reportes = ""
    df_limpio = df_filtrado[['id_prestamo','motivo','observaciones']].dropna(subset=['motivo']).tail(40)

    for idx, row in df_limpio.iterrows():
        obs = row['observaciones'] if row['observaciones'] else "Sin observaciones"
        reportes += f"ID:{row['id_prestamo']} - Mtv: {row['motivo']} (Obs: {obs}) | "
    
    prompt = f"""
    Eres un auditor financiero y analista de bienestar laboral. Analiza las causales de solicitudes de préstamos de los empleados y clasifícalas en 5 categorías de destino de fondos.

    Datos a evaluar: {reportes}

    Responde ÚNICAMENTE un formato JSON estricto con esta estructura exacta:
    {{
        "Categorias": {{"Salud / Emergencia Médica": 10, "Remodelación / Vivienda": 5, "Gastos Escolares": 3, "Consolidación de Deuda": 2, "Imprevistos Personales": 1}},
        "Asignaciones": {{"Salud / Emergencia Médica": [101, 102], "Remodelación / Vivienda": [103], "Gastos Escolares": [], "Consolidación de Deuda": [], "Imprevistos Personales": []}}
    }}
    Donde los números en 'Asignaciones' son los 'ID' de préstamo enviados.
    """

    try:
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        texto_limpio = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error en el motor anal[itico de AI: {e}")
        return None

def analizar_motivos_horas_extras_ia(df_filtrado):
    if df_filtrado.empty:
        return None

    reportes = ""
    # 🟢 CORREGIDO: Usamos 'motivo' en lugar de 'motivo_hraExtra'
    df_limpio = df_filtrado[['id_horaextra', 'motivo', 'observaciones']].dropna(subset=['motivo']).tail(40)

    for idx, row in df_limpio.iterrows():
        obs = row['observaciones'] if row['observaciones'] else "Sin observaciones"
        reportes += f"ID:{row['id_horaextra']} - Mtv: {row['motivo']} (Obs: {obs}) | "
    
    prompt = f"""
    Eres un auditor operacional de Recursos Humanos. Analiza las razones y motivos de horas extras trabajadas por los empleados y clasifícalas estrictamente en 5 categorías de causa operativa.

    Datos a evaluar: {reportes}

    Responde ÚNICAMENTE un formato JSON estricto con esta estructura exacta, sin textos adicionales:
    {{
        "Categorias": {{"Picos de Producción / Cosecha": 12, "Cobertura de Vacantes / Ausencias": 5, "Mantenimiento / Maquinaria": 4, "Cierres Administrativos / Inventario": 3, "Otros Imprevistos": 1}},
        "Asignaciones": {{"Picos de Producción / Cosecha": [1, 2], "Cobertura de Vacantes / Ausencias": [3], "Mantenimiento / Maquinaria": [], "Cierres Administrativos / Inventario": [], "Otros Imprevistos": []}}
    }}
    Donde los números en 'Asignaciones' son los 'ID' de hora extra enviados.
    """

    try:
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        texto_limpio = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error en el motor analítico de IA: {e}")
        return None


def analizar_motivos_permisos_ia(df_filtrado):
    if df_filtrado.empty:
        return None

    reportes = ""
    df_limpio = df_filtrado[['id_permiso', 'motivo', 'observaciones']].dropna(subset=['motivo']).tail(40)

    for idx, row in df_limpio.iterrows():
        obs = row['observaciones'] if row['observaciones'] else "Sin observaciones"
        reportes += f"ID:{row['id_permiso']} - Mtv: {row['motivo']} (Obs: {obs}) | "
    
    prompt = f"""
    Eres un especialista en Recursos Humanos. Analiza las razones y motivos de permisos laborales solicitados y clasifícalos estrictamente en 5 categorías de causa personal u operacional.

    Datos a evaluar: {reportes}

    Responde ÚNICAMENTE un formato JSON estricto con esta estructura exacta, sin textos adicionales:
    {{
        "Categorias": {{"Asuntos Personales / Familiares": 10, "Citas Médicas / Salud": 6, "Trámites Oficiales / Legales": 4, "Luto / Emergencia": 2, "Otros Motivos": 1}},
        "Asignaciones": {{"Asuntos Personales / Familiares": [1, 2], "Citas Médicas / Salud": [3], "Trámites Oficiales / Legales": [], "Luto / Emergencia": [], "Otros Motivos": []}}
    }}
    Donde los números en 'Asignaciones' son los 'ID' de permiso enviados.
    """

    try:
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        texto_limpio = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error en el motor analítico de IA: {e}")
        return None

def analizar_motivos_sanciones_ia(df_filtrado):
    if df_filtrado.empty:
        return None

    reportes = ""
    df_limpio = df_filtrado[['id_sancion', 'motivo', 'observaciones']].dropna(subset=['motivo']).tail(40)

    for idx, row in df_limpio.iterrows():
        obs = row['observaciones'] if row['observaciones'] else "Sin observaciones"
        reportes += f"ID:{row['id_sancion']} - Mtv: {row['motivo']} (Obs: {obs}) | "
    
    prompt = f"""
    Eres un especialista en relaciones laborales y derecho del trabajo. Analiza las faltas y motivos de sanciones aplicadas al personal y clasifícalas estrictamente en 5 categorías de falta disciplinaria.

    Datos a evaluar: {reportes}

    Responde ÚNICAMENTE un formato JSON estricto con esta estructura exacta, sin textos adicionales:
    {{
        "Categorias": {{"Retardos / Faltas Injustificadas": 10, "Incumplimiento de Protocolo / Seguridad": 6, "Mal Uso de Equipo / Propiedad": 4, "Faltas de Respeto / Conducta": 2, "Otras Incidencias Disciplinarias": 1}},
        "Asignaciones": {{"Retardos / Faltas Injustificadas": [1, 2], "Incumplimiento de Protocolo / Seguridad": [3], "Mal Uso de Equipo / Propiedad": [], "Faltas de Respeto / Conducta": [], "Otras Incidencias Disciplinarias": []}}
    }}
    Donde los números en 'Asignaciones' son los 'ID' de sanción enviados.
    """

    try:
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        texto_limpio = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error en el motor analítico de IA: {e}")
        return None


# --- ESTILOS CSS ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>

    /* 1. Fondo de las etiquetas/chips seleccionadas en Multiselect */
    span[data-baseweb="tag"] {
        background-color: #247A38 !important;
        color: #FFFFFF !important;
        border-radius: 6px !important;
        border: none !important;
        font-weight: 500 !important;
        padding: 4px 8px !important;
    }

    /* Color e interacción de la 'X' para eliminar etiqueta */
    span[data-baseweb="tag"] span[role="button"] {
        color: #FFFFFF !important;
    }
    span[data-baseweb="tag"] span[role="button"]:hover {
        background-color: rgba(255, 255, 255, 0.2) !important;
        border-radius: 50% !important;
    }

    /* 2. Caja contenedora del Select / Multiselect (Sin bordes) */
    div[data-baseweb="select"] > div {
        background-color: #0E1117 !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 8px !important;
    }

    div[data-baseweb="select"]:hover > div,
    div[data-baseweb="select"]:focus-within > div {
        border: none !important;
        box-shadow: none !important;
    }

    /* 3. Menú desplegable de opciones */
    ul[data-baseweb="menu"] {
        background-color: #161B22 !important;
        border: 1px solid #247A38 !important;
    }

    li[data-baseweb="option"] {
        color: #FFFFFF !important;
    }
    li[data-baseweb="option"]:hover,
    li[data-baseweb="option"][aria-selected="true"] {
        background-color: #247A38 !important;
        color: #FFFFFF !important;
    }

    div[data-baseweb="select"] svg {
        fill: #9CA3AF !important;
    }

    /* Checkboxes y Títulos del Sidebar */
    div[data-baseweb="checkbox"] input:checked + div {
        background-color: #2F9946 !important;
        border-color: #2F9946 !important;
    }

    .stSidebar .stMarkdown h1, .stSidebar .stMarkdown h2, .stSidebar .stMarkdown h3 {
        color: #2F9946 !important;
    }

    /* ==========================================================
       ESTILO DE PESTAÑAS (TABS VERDES)
    ========================================================== */
    div[data-testid="stTabs"] { 
        margin-top: 15px !important; 
    }

    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        padding: 8px 16px !important;
    }

    button[data-baseweb="tab"] p {
        font-size: 18px !important;
        font-weight: 600 !important;
        color: #D1D5DB !important;
        transition: color 0.2s ease-in-out !important;
    }

    button[data-baseweb="tab"]:hover p {
        color: #2F9946 !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #2F9946 !important;
        font-weight: bold !important;
    }

    div[data-baseweb="tab-highlight"] {
        background-color: #2F9946 !important;
        height: 3px !important;
    }

    /* ==========================================================
       BOTONES INTERACTIVOS DE DIAPOSITIVAS
    ========================================================== */
    button[data-testid="baseButton-primary"] {
        background-color: rgba(46, 125, 50, 0.20) !important;
        color: #A9DFBF !important;
        border: 1px solid rgba(46, 125, 50, 0.4) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.2s ease-in-out !important;
    }
    button[data-testid="baseButton-primary"]:hover {
        background-color: rgba(46, 125, 50, 0.40) !important;
        color: #FFFFFF !important;
        border: 1px solid #2E7D32 !important;
    }
    button[data-testid="baseButton-primary"] p, 
    button[data-testid="baseButton-primary"]:hover p { 
        color: #FFFFFF !important; 
    }

    div[data-testid="stVerticalBlockWrapper"] button:last-of-type {
        background-color: rgba(230, 57, 70, 0.15) !important;
        color: #FADBD8 !important;
        border: 1px solid rgba(230, 57, 70, 0.4) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div[data-testid="stVerticalBlockWrapper"] button:last-of-type:hover {
        background-color: rgba(230, 57, 70, 0.35) !important;
        color: #FFFFFF !important;
        border: 1px solid #E63946 !important;
    }

    /* ==========================================================
       ESTILO RESTABLECIDO Y ANIMADO PARA METRIC-CARDS
    ========================================================== */
    .metric-card {
        background-color: #12161A !important;
        border-radius: 10px !important;
        padding: 16px 20px !important;
        display: flex !important;
        align-items: center !important;
        gap: 18px !important;
        border-left: 5px solid var(--card-color, #2F9946) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
        transition: all 0.3s ease-in-out !important;
        cursor: pointer !important;
        margin-bottom: 10px !important;
        height: auto !important;
    }

    /* Efecto Hover en Cards */
    .metric-card:hover {
        transform: translateY(-4px) !important;
        background-color: #1A2026 !important;
        box-shadow: 0 8px 20px rgba(47, 153, 70, 0.35), 
                    -3px 0 12px var(--card-color, #2F9946) !important;
    }

    .metric-icon {
        font-size: 2rem !important;
        color: var(--card-color, #2F9946) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: transform 0.3s ease !important;
    }

    .metric-card:hover .metric-icon {
        transform: scale(1.15) !important;
    }

    .metric-content {
        display: flex !important;
        flex-direction: column !important;
    }

    .metric-title {
        color: #9CA3AF !important;
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
    }

    .metric-value {
        color: #FFFFFF !important;
        font-size: 1.5rem !important;
        font-weight: 800 !important;
        margin-top: 2px !important;
    }

</style>
""", unsafe_allow_html=True)

#Inicializar Datos
df_raw = dict_rrhh.get("vacaciones", pd.DataFrame())

# --- 3. BARRA LATERAL CON FILTROS DINAMICOS ---
st.sidebar.title("🎯 Filtros de Datos")

if not df_raw.empty:
    años_disp = sorted(df_raw['año'].dropna().unique().astype(int), reverse=True)
    f_año = st.sidebar.multiselect("Año:", años_disp, default=años_disp[:1])

    df_temp_mes = df_raw[df_raw['año'].isin(f_año)]
    meses_disp = df_temp_mes.sort_values('mes_sort')['mes_nombre'].unique()
    f_mes = st.sidebar.multiselect("Mes:",meses_disp, default=meses_disp)

    df_temp_ubi = df_raw[(df_raw['año'].isin(f_año)) & (df_raw['mes_nombre'].isin(f_mes))]
    ubis_disp = sorted(df_temp_ubi['ubicacion'].unique())
    f_ubi = st.sidebar.multiselect("📍Ubicacion:",ubis_disp,default=ubis_disp)

    # --- APLICACION COMPLETA DE FILTROS ---
    df_res = df_raw[
        (df_raw['año'].isin(f_año)) &
        (df_raw['mes_nombre'].isin(f_mes)) &
        (df_raw['ubicacion'].isin(f_ubi))
    ].copy()
else:
    df_res = pd.DataFrame()
    f_año, f_mes, f_ubi = [], [], []

config_plotly = {'displayModeBar': True, 'displaylogo': False, 'scrollZoom': True }


# ==========================================
# 5. ESTRUCTURA DE PESTAÑAS PRINCIPALES
# ==========================================
tab_vacaciones, tab_prestamos, tab_horas_extras, tab_permisos, tab_sanciones = st.tabs(["🏖️ Vacaciones", "💰 Préstamos", "⏰ Horas Extras", "📝 Permisos", "⚖️ Sanciones"])

#-------------------------------------------
# TAB 1: CONTROL DE VACACIONES
# ------------------------------------------
with tab_vacaciones:
    if not df_res.empty:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)

        total_solicitudes = len(df_res)
        total_dias = df_res['dias_vacacion'].sum()
        pendientes = len(df_res[df_res['estatus'].astype(str).str.upper().str.strip() == 'PENDIENTE'])
        promedio_dias = df_res['dias_vacacion'].mean() if total_solicitudes > 0 else 0

        with col_m1:
            st.markdown(create_card("fa-clipboard-list", "Total Solicitudes", f"{total_solicitudes} Registros"), unsafe_allow_html=True)
        with col_m2:
            st.markdown(create_card("fa-calendar-days", "Días Autorizados", f"{total_dias} Días Totales"), unsafe_allow_html=True)
        with col_m3:
            st.markdown(create_card("fa-business-time", "Pendientes por Validar", f"{pendientes} Órdenes"), unsafe_allow_html=True)
        with col_m4:
            st.markdown(create_card("fa-calculator", "Promedio por Salida", f"{promedio_dias:.1f} Días"), unsafe_allow_html=True)
    
        st.divider()

        # --- CONSTRUCCIÓN DE GRÁFICAS DE VACACIONES ---
        emp_data = df_res.groupby('empleado')['dias_vacacion'].sum().nlargest(10).sort_values()
        fig_empleados = go.Figure(go.Bar(
            y=emp_data.index, x=emp_data.values, orientation='h', marker_color='#1D3557',
            text=[f"{d} dias" for d in emp_data.values], textposition='outside'
        ))
        fig_empleados.update_layout(
            title=dict(text="<b>📊 Top 10 Empleados con Mayor Consumo de Vacaciones</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10)
        )

        
        
        meses_espanol = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }
        
        # 1. Agrupamos por Año y Mes usando Periodo Mensual para conservar el orden cronológico estricto
        df_res['periodo_m'] = df_res['fecha_inicio'].dt.to_period('M')
        
        periodo_data = df_res.groupby('periodo_m')['dias_vacacion'].sum().reset_index()
        periodo_data = periodo_data.sort_values('periodo_m')

        # 2. Formateamos la etiqueta visible como 'Ene-25', 'Ene-26'
        def formatear_mes_año(periodo):
            mes_num = periodo.month
            año_abbr = str(periodo.year)[-2:] # Obtiene los últimos 2 dígitos del año (ej. 25, 26)
            nom_mes = meses_espanol.get(mes_num, '')
            return f"{nom_mes}-{año_abbr}"

        periodo_data['Mes_Año'] = periodo_data['periodo_m'].apply(formatear_mes_año)

        fig_periodos = px.area(
            periodo_data, 
            x='Mes_Año', 
            y='dias_vacacion',
            title="📈 <b>Picos de Demanda: Distribución de Días por Periodo</b>",
            markers=True, 
            color_discrete_sequence=['#2E7D32'],
            labels={'Mes_Año': 'Mes', 'dias_vacacion': 'Días Solicitados'}
        )
        fig_periodos.update_layout(
            template="plotly_dark", 
            margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(
                title="Mes", 
                type='category' # Mantiene el orden exacto del DataFrame ordenado
            ),
            yaxis=dict(title="Días Solicitados")
        )

        df_gantt = df_res.sort_values('fecha_inicio').tail(25).copy()
        meses_es = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        # Función helper para dar formato: "7 días del 16 al 23 Jun"
        def armar_etiqueta_gantt(row):
            f_ini = row['fecha_inicio']
            f_fin = row['fecha_fin']
            dias = int(row['dias_vacacion']) if pd.notnull(row['dias_vacacion']) else 0
            
            if pd.notnull(f_ini) and pd.notnull(f_fin):
                dia_i = f_ini.day
                dia_f = f_fin.day
                mes_i = meses_es.get(f_ini.month, '')
                mes_f = meses_es.get(f_fin.month, '')
                
                # Si el inicio y fin ocurren en el mismo mes
                if f_ini.month == f_fin.month:
                    return f"{dias} días del {dia_i} al {dia_f} {mes_i}"
                else:
                    return f"{dias} días del {dia_i} {mes_i} al {dia_f} {mes_f}"
            return f"{dias} días"

        df_gantt['etiqueta_dias_fechas'] = df_gantt.apply(armar_etiqueta_gantt, axis=1)

        # 2. 🚨 ALGORITMO DE DETECCIÓN DE TRASLAPES DE FECHAS
        empleados_traslapados = set()
        records = df_gantt.to_dict('records')

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                r1, r2 = records[i], records[j]
                # Verificamos si las fechas de inicio y fin se cruzan entre sí
                if (r1['fecha_inicio'] <= r2['fecha_fin']) and (r1['fecha_fin'] >= r2['fecha_inicio']):
                    empleados_traslapados.add(r1['empleado'])
                    empleados_traslapados.add(r2['empleado'])

        fig_traslapes = px.timeline(
            df_gantt, 
            x_start="fecha_inicio", 
            x_end="fecha_fin", 
            y="empleado", 
            color="ubicacion",
            title="🗓️ <b>Matriz de Coincidencias: Traslapes y Días de Personal</b>",
            text="etiqueta_dias_fechas", # 🟢 Ahora muestra la duración y las fechas sobre la barra
            color_discrete_sequence=px.colors.qualitative.Safe,
            hover_data={
                "motivo": True,
                "dias_vacacion": True,
                "etiqueta_dias_fechas": False
            }
        )

        # 4. 🎨 RESALTAR EMPLEADOS EN EL EJE Y
        # Creamos etiquetas personalizadas con HTML/CSS para cambiar el color de los nombres con traslape
        orden_empleados = df_gantt['empleado'].unique()
        tick_labels_resaltados = []

        for emp in orden_empleados:
            if emp in empleados_traslapados:
                # 🟡 Resaltado en Dorado con Alerta si se cruza con alguien más
                tick_labels_resaltados.append(f"<span style='color: #FFD700; font-weight: bold;'>⚠️ {emp}</span>")
            else:
                # ⚪ Blanco/Gris normal si no interfiere con nadie
                tick_labels_resaltados.append(f"<span style='color: #E0E0E0;'>{emp}</span>")

        fig_traslapes.update_yaxes(
            autorange="reversed",
            tickmode='array',
            tickvals=list(orden_empleados),
            ticktext=tick_labels_resaltados
        )

        fig_traslapes.update_layout(
            template="plotly_dark", 
            margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Calendario Operativo", type='date'),
            yaxis=dict(title="Personal en Vacaciones")
        )

        #disponibles_data = df_res.groupby('empleado')['dias_disponibles'].first().nlargest(10).sort_values()
        #fig_disponibles = go.Figure(go.Bar(
            #y=disponibles_data.index, x=disponibles_data.values, orientation='h', marker_color='#2E7D32',
            #text=[f"{int(d)} días disp." for d in disponibles_data.values], textposition='outside'
        #))
        #fig_disponibles.update_layout(
            #title=dict(text="📊 <b>Top 10 Colaboradores con Mayor Saldo de Vacaciones</b>", font=dict(size=16, color="white")),
            #template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10)
        #)

        # --- LIENZO INTERACTIVO VACACIONES ---
        if 'v_graficas_activas' not in st.session_state:
            st.session_state['v_graficas_activas'] = []
        
        col_lienzo, col_miniaturas = st.columns([4, 1])

        with col_miniaturas:
            st.markdown("<h5 style='text-align: center; color: #FFFFFF;'>📊 Diapositivas</h5>", unsafe_allow_html=True)

            btn_emp = "primary" if "empleados" in st.session_state['v_graficas_activas'] else "secondary"
            if st.button("👥 Top Empleados", use_container_width=True, type=btn_emp):
                if "empleados" in st.session_state['v_graficas_activas']: st.session_state['v_graficas_activas'].remove("empleados")
                else: st.session_state['v_graficas_activas'].append("empleados")
                st.rerun()

            btn_per = "primary" if "periodos" in st.session_state['v_graficas_activas'] else "secondary"
            if st.button("📈 Períodos de Demanda", use_container_width=True, type=btn_per):
                if "periodos" in st.session_state['v_graficas_activas']: st.session_state['v_graficas_activas'].remove("periodos")
                else: st.session_state['v_graficas_activas'].append("periodos")
                st.rerun()

            btn_tra = "primary" if "traslapes" in st.session_state['v_graficas_activas'] else "secondary"
            if st.button("🗓️ Traslapes de Personal", use_container_width=True, type=btn_tra):
                if "traslapes" in st.session_state['v_graficas_activas']: st.session_state['v_graficas_activas'].remove("traslapes")
                else: st.session_state['v_graficas_activas'].append("traslapes")
                st.rerun()

            #btn_disp = "primary" if "disponibles" in st.session_state['v_graficas_activas'] else "secondary"
            #if st.button("📊 Días Disponibles", use_container_width=True, type=btn_disp):
                #if "disponibles" in st.session_state['v_graficas_activas']: st.session_state['v_graficas_activas'].remove("disponibles")
                #else: st.session_state['v_graficas_activas'].append("disponibles")
                #st.rerun()
            
            st.write("---")
            if st.button("🗑️ Limpiar Pantalla", type="secondary", use_container_width=True):
                st.session_state['v_graficas_activas'] = []
                st.rerun()

        with col_lienzo: 
            lista_v = st.session_state['v_graficas_activas']

            if not lista_v:
                st.info("⬅️ Selecciona una o más gráficas del panel analítico derecho para proyectarlas en el tablero.")
            elif len(lista_v) == 1:
                g = lista_v[0]
                if g == "empleados": st.plotly_chart(fig_empleados, use_container_width=True, config=config_plotly)
                elif g == "periodos": st.plotly_chart(fig_periodos, use_container_width=True, config=config_plotly)
                elif g == "traslapes": st.plotly_chart(fig_traslapes, use_container_width=True, config=config_plotly)
                #elif g == "disponibles": st.plotly_chart(fig_disponibles, use_container_width=True, config=config_plotly)
            else:
                # Si 'traslapes' está activo, lo separamos para que sea ancho completo abajo
                tiene_traslapes = "traslapes" in lista_v
                lista_sin_traslapes = [g for g in lista_v if g != "traslapes"]

                # 1. Dibujamos las demás gráficas en pares (2 columnas)
                if lista_sin_traslapes:
                    cols_render = st.columns(2)
                    for i, g in enumerate(lista_sin_traslapes):
                        with cols_render[i % 2]:
                            if g == "empleados": st.plotly_chart(fig_empleados, use_container_width=True, config=config_plotly)
                            elif g == "periodos": st.plotly_chart(fig_periodos, use_container_width=True, config=config_plotly)
                            #elif g == "disponibles": st.plotly_chart(fig_disponibles, use_container_width=True, config=config_plotly)

                if tiene_traslapes:
                    st.plotly_chart(fig_traslapes, use_container_width=True, config=config_plotly)
        
        st.write("---")
        st.markdown("### 🧠 Análisis de Contexto y Bienestar Laboral (IA)")

        col_btn_ia, col_info_ia = st.columns([1, 3])
        with col_btn_ia:
            procesar_ia = st.button("🚀 Procesar Motivos con Gemini", use_container_width=True)
        with col_info_ia:
            st.info("El modelo cognitivo categoriza el texto libre de las solicitudes para identificar tendencias de salud o descanso.")

        if procesar_ia:
            with st.spinner("Gemini está categorizando las solicitudes de personal..."):
                resultado_rrhh = analizar_motivos_vacaciones_ia(df_res)
                if resultado_rrhh:
                    st.session_state['res_ia_vacaciones'] = resultado_rrhh
            
        if 'res_ia_vacaciones' in st.session_state:
            res_v = st.session_state['res_ia_vacaciones']
            dict_grafica = res_v.get('Categorias', {})
            
            df_ia_v = pd.DataFrame(list(dict_grafica.items()), columns=['Contexto de Salida', 'Casos']).sort_values('Casos')
            fig_ia_v = px.bar(df_ia_v, x='Casos', y='Contexto de Salida', orientation='h', title="🎯 Clasificación Semántica de Motivos de Ausencia", color_discrete_sequence=['#FFD700'])
            fig_ia_v.update_layout(template="plotly_dark", clickmode='event+select', margin=dict(l=10, r=10, t=50, b=10))

            cont_resultados_ia = st.container()
            with cont_resultados_ia:
                if 'cat_vac_seleccionada' not in st.session_state:
                    st.session_state['cat_vac_seleccionada'] = None

                if st.session_state['cat_vac_seleccionada']:
                    col_g_ia, col_t_ia = st.columns(2)
                else:
                    col_g_ia = st.container()
                    col_t_ia = None

                with col_g_ia:
                    evento_click = st.plotly_chart(fig_ia_v, use_container_width=True, on_select="rerun")
                
                if evento_click and len(evento_click["selection"]["points"]) > 0:
                    st.session_state['cat_vac_seleccionada'] = evento_click["selection"]["points"][0]["y"]
                else:
                    st.session_state['cat_vac_seleccionada'] = None

                if st.session_state['cat_vac_seleccionada'] and col_t_ia is not None:
                    cat_actual = st.session_state['cat_vac_seleccionada']
                    ids_asociados = res_v.get('Asignaciones', {}).get(cat_actual, [])
                    
                    with col_t_ia:
                        st.markdown(f"##### 📂 Personal indexado en: {cat_actual}")
                        df_res_id = df_res.set_index('id_vacacion')
                        ids_existentes = [idx for idx in ids_asociados if idx in df_res_id.index]
                        
                        if ids_existentes:
                            df_detalle_v = df_res_id.loc[ids_existentes]
                            st.dataframe(df_detalle_v[['empleado', 'motivo', 'fecha_inicio', 'dias_vacacion']], use_container_width=True, hide_index=True, height=280)
                        else:
                            st.warning("Los registros no coinciden con los filtros aplicados.")
        else:
            st.warning("⚠️ No se encontraron registros de vacaciones con los filtros seleccionados.")


# ------------------------------------------
# TAB 2: PRÉSTAMOS
# ------------------------------------------   
with tab_prestamos:
    df_p_raw = dict_rrhh.get("prestamos", pd.DataFrame())

    if not df_p_raw.empty and f_año:
        df_p_res = df_p_raw[
            (df_p_raw['año'].isin(f_año)) &
            (df_p_raw['mes_nombre'].isin(f_mes)) &
            (df_p_raw['ubicacion'].isin(f_ubi))
        ].copy()
    else:
        df_p_res = pd.DataFrame()

    if not df_p_res.empty:
        # --- METRICAS SUPERIORES PRÉSTAMOS ---
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)

        monto_total = df_p_res['cantidad_autorizada'].sum()
        retencion_semanal = df_p_res['descuento_semanal'].sum()
        p_autorizadas = len(df_p_res[df_p_res['estatus'].astype(str).str.upper().str.strip().isin(['ACEPTADA'])])
        p_pendientes = len(df_p_res[df_p_res['estatus'].astype(str).str.upper().str.strip() == 'EN REVISION'])

        with col_p1: 
            st.markdown(create_card("fa-sack-dollar", "Capital Otorgado", f"${monto_total:,.2f}"), unsafe_allow_html=True)
        with col_p2:
            st.markdown(create_card("fa-hand-holding-dollar", "Deducción Semanal", f"${retencion_semanal:,.2f}"), unsafe_allow_html=True)
        with col_p3:
            st.markdown(create_card("fa-circle-check", "Solicitudes Autorizadas", f"{p_autorizadas} Préstamos"), unsafe_allow_html=True)
        with col_p4:
            st.markdown(create_card("fa-file-invoice-dollar", "Por Autorizar", f"{p_pendientes} Solicitudes"), unsafe_allow_html=True)
        st.divider()

        # --- CONSTRUCCIÓN DE GRÁFICAS DE PRÉSTAMOS ---
        p_emp_data = df_p_res.groupby('empleado')['cantidad_autorizada'].sum().nlargest(10).sort_values()
        fig_p_empleados = go.Figure(go.Bar(
            y=p_emp_data.index, x=p_emp_data.values, orientation='h', marker_color='#1D3557',
            text=[f"${x:,.0f}" for x in p_emp_data.values], textposition='outside'
        ))
        fig_p_empleados.update_layout(
            title=dict(text="<b>💰 Top 10 Empleados con Mayor Capital Autorizado</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10)
        )

        # 2. Flujo Mensual: Gráfica Mixta (Barras + Línea con Eje Y Dual)
        # 2. Flujo Mensual: Gráfica Mixta (Barras + Línea con Eje Y Dual)
        p_hist_data = df_p_res.groupby(['mes_sort', 'mes_nombre']).agg(
            solicitudes=('id_prestamo', 'count'),
            monto_total=('cantidad_autorizada', 'sum')
        ).reset_index().sort_values('mes_sort')

        fig_p_hist = go.Figure()

        # 🟢 1. Barras Celestes para Solicitudes (Eje Y Izquierdo)
        fig_p_hist.add_trace(go.Bar(
            x=p_hist_data['mes_nombre'],
            y=p_hist_data['solicitudes'],
            name="Solicitudes Registradas",
            marker_color='#A8DADC',
            #text=[f"{n} sol." for n in p_hist_data['solicitudes']],
            #textposition='outside',
            #cliponaxis=False, # 👈 Evita que el texto de arriba se corte con el borde
            hovertemplate="📋 Préstamos: %{y} préstamos<extra></extra>"
        ))

        # 🟢 2. Línea Roja para Monto Financiado (Eje Y Derecho)
        fig_p_hist.add_trace(go.Scatter(
            x=p_hist_data['mes_nombre'],
            y=p_hist_data['monto_total'],
            name="Monto Dispersado ($)",
            yaxis="y2",
            mode='lines+markers',
            line=dict(color='#E63946', width=3),
            marker=dict(size=8, color='#E63946'),
            hovertemplate="💰 Monto: $%{y:,.2f}<extra></extra>"
        ))

        # 🟢 3. Layout Doble Eje Y
        # 🟢 CORREGIDO: Cambiamos 'orient' por 'orientation'
        fig_p_hist.update_layout(
            title=dict(text="<b>📅 Flujo Mensual: Solicitudes de Crédito vs. Monto Otorgado</b>", font=dict(size=16, color="white")),
            template="plotly_dark",
            hovermode="x unified",
            margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Mes"),
            yaxis=dict(
                title="Número de Solicitudes",
                showgrid=True,
                range=[0, p_hist_data['solicitudes'].max() * 1.35 if not p_hist_data.empty else 10]
            ),
            yaxis2=dict(
                title="Monto Dispersado ($)",
                overlaying="y",
                side="right",
                tickprefix="$",
                showgrid=False
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1) # 👈 AQUÍ EL CAMBIO
        )

        p_est_data = df_p_res.groupby('estatus').size()
        colores_p_est = {'APROBADO': '#2F9946', 'PENDIENTE': '#AFB030', 'RECHAZADO': '#E63030'}
        #fig_p_estatus = go.Figure(go.Bar(
            #x=p_est_data.index, y=p_est_data.values,
            #marker_color=[colores_p_est.get(str(x).upper().strip(), '#A8A8A8') for x in p_est_data.index],
            #text=p_est_data.values, textposition='outside'
        #))
        #fig_p_estatus.update_layout(
            #title=dict(text="<b>🚨 Estatus de Solicitudes de Crédito Interno</b>", font=dict(size=16, color="white")),
            #template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10)
        #)

        # 4. Top 5 Ubicaciones con Mayor Demanda de Préstamos
        p_ubi_data = df_p_res.groupby('ubicacion').agg(
            total_solicitudes=('id_prestamo', 'count'),
            monto_total=('cantidad_autorizada', 'sum')
        ).nlargest(5, 'monto_total').sort_values('monto_total')  # 🟢 Ordenado por monto_total monetario

        fig_p_ubicaciones = go.Figure(go.Bar(
            y=p_ubi_data.index,
            x=p_ubi_data['monto_total'],  # 🟢 El eje X ahora representa el costo monetario
            orientation='h',
            marker_color='#457B9D',
            text=[f"${m:,.2f} ({n} sol.)" for n, m in zip(p_ubi_data['total_solicitudes'], p_ubi_data['monto_total'])],
            textposition='outside',
            cliponaxis=False,
            customdata=p_ubi_data['total_solicitudes'].values,
            hovertemplate="📍 <b>Ubicación:</b> %{y}<br>" +
                          "💰 <b>Monto Total Dispersado:</b> $%{x:,.2f}<br>" +
                          "📋 <b>Cantidad de Solicitudes:</b> %{customdata} solicitudes<extra></extra>"
        ))
        fig_p_ubicaciones.update_layout(
            title=dict(text="<b>📍 Top 5 Ubicaciones por Monto Monetario Otorgado en Préstamos</b>", font=dict(size=16, color="white")),
            template="plotly_dark",
            margin=dict(l=10, r=130, t=50, b=10),
            xaxis=dict(
                title="Monto Total Dispersado ($)", 
                tickprefix="$",
                range=[0, p_ubi_data['monto_total'].max() * 1.35 if not p_ubi_data.empty else 10000]
            )
        )

        # --- LIENZO INTERACTIVO PRÉSTAMOS ---
        if 'p_graficas_activas' not in st.session_state:
            st.session_state['p_graficas_activas'] = []
        
        col_p_lienzo, col_p_miniaturas = st.columns([4, 1])

        with col_p_miniaturas:
            st.markdown("<h5 style='text-align: center; color: #FFFFFF;'>📊 Diapositivas</h5>", unsafe_allow_html=True)
            
            btn_p_emp = "primary" if "p_empleados" in st.session_state['p_graficas_activas'] else "secondary"
            if st.button("👥 Capital por Empleado", use_container_width=True, type=btn_p_emp, key="btn_p_emp"):
                if "p_empleados" in st.session_state['p_graficas_activas']: st.session_state['p_graficas_activas'].remove("p_empleados")
                else: st.session_state['p_graficas_activas'].append("p_empleados")
                st.rerun()

            btn_p_his = "primary" if "p_historico" in st.session_state['p_graficas_activas'] else "secondary"
            if st.button("📅 Flujo Mensual", use_container_width=True, type=btn_p_his, key="btn_p_flujo"): # 👈 KEY ÚNICO
                if "p_historico" in st.session_state['p_graficas_activas']: st.session_state['p_graficas_activas'].remove("p_historico")
                else: st.session_state['p_graficas_activas'].append("p_historico")
                st.rerun()

            btn_p_ubi = "primary" if "p_ubicaciones" in st.session_state['p_graficas_activas'] else "secondary"
            if st.button("📍 Top Ubicaciones", use_container_width=True, type=btn_p_ubi, key="btn_p_ubi"):
                if "p_ubicaciones" in st.session_state['p_graficas_activas']: st.session_state['p_graficas_activas'].remove("p_ubicaciones")
                else: st.session_state['p_graficas_activas'].append("p_ubicaciones")
                st.rerun()

            #btn_p_est = "primary" if "p_estatus" in st.session_state['p_graficas_activas'] else "secondary"
            #if st.button("🚨 Control Estatus", use_container_width=True, type=btn_p_est, key="btn_p_est"):
                #if "p_estatus" in st.session_state['p_graficas_activas']: st.session_state['p_graficas_activas'].remove("p_estatus")
                #else: st.session_state['p_graficas_activas'].append("p_estatus")
                #st.rerun()

            st.write("---")
            if st.button("🗑️ Limpiar Pantalla", type="secondary", use_container_width=True, key="btn_p_limpiar"):
                st.session_state['p_graficas_activas'] = []
                st.rerun()

        with col_p_lienzo:
            lista_p = st.session_state['p_graficas_activas']

            if not lista_p:
                st.info("⬅️ Selecciona una o más perspectivas financieras del panel derecho para proyectarlas en el tablero.")
            
            elif len(lista_p) == 1:
                g = lista_p[0]
                if g == "p_empleados": st.plotly_chart(fig_p_empleados, use_container_width=True, config=config_plotly)
                elif g == "p_historico": st.plotly_chart(fig_p_hist, use_container_width=True, config=config_plotly)
                #elif g == "p_estatus": st.plotly_chart(fig_p_estatus, use_container_width=True, config=config_plotly)
                elif g == "p_ubicaciones": st.plotly_chart(fig_p_ubicaciones, use_container_width=True, config=config_plotly) # 👈 AÑADIDO
            else:
                # Verificamos si 'p_historico' está entre las seleccionadas
                tiene_historico = "p_historico" in lista_p
                lista_sin_historico = [g for g in lista_p if g != "p_historico"]

                # 1. Renderizamos las demás gráficas en pares (2 columnas)
                if lista_sin_historico:
                    cols_p_render = st.columns(2)
                    for i, g in enumerate(lista_sin_historico):
                        with cols_p_render[i % 2]:
                            if g == "p_empleados": st.plotly_chart(fig_p_empleados, use_container_width=True, config=config_plotly)
                            #elif g == "p_estatus": st.plotly_chart(fig_p_estatus, use_container_width=True, config=config_plotly)
                            elif g == "p_ubicaciones": st.plotly_chart(fig_p_ubicaciones, use_container_width=True, config=config_plotly)

                # 2. Si 'p_historico' estaba seleccionado, lo dibujamos abajo a ANCHO COMPLETO (100%)
                if tiene_historico:
                    st.plotly_chart(fig_p_hist, use_container_width=True, config=config_plotly)

        # --- SECCIÓN INFERIOR IA PRÉSTAMOS ---
        st.write("---")
        st.markdown("### 🧠 Destino del Capital Interno - Auditoría Cognitiva (IA)")
        
        col_p_btn_ia, col_p_info_ia = st.columns([1, 3])
        with col_p_btn_ia:
            procesar_p_ia = st.button("🚀 Analizar Destino de Fondos", use_container_width=True)
        with col_p_info_ia:
            st.info("Gemini analiza las causales y observaciones para mapear en qué están invirtiendo el capital los trabajadores.")

        if procesar_p_ia:
            with st.spinner("Mapeando flujo de capital con Gemini..."):
                resultado_p_rrhh = analizar_motivos_prestamos_ia(df_p_res)
                if resultado_p_rrhh:
                    st.session_state['res_ia_prestamos'] = resultado_p_rrhh
        
        if 'res_ia_prestamos' in st.session_state:
            res_p = st.session_state['res_ia_prestamos']
            dict_p_grafica = res_p.get('Categorias', {})
            
            df_p_ia = pd.DataFrame(list(dict_p_grafica.items()), columns=['Causal de Crédito', 'Casos']).sort_values('Casos')
            fig_p_ia = px.bar(df_p_ia, x='Casos', y='Causal de Crédito', orientation='h', title="🎯 Clasificación Semántica del Destino de Préstamos", color_discrete_sequence=['#FFD700'])
            fig_p_ia.update_layout(template="plotly_dark", clickmode='event+select', margin=dict(l=10, r=10, t=50, b=10))

            cont_p_resultados_ia = st.container()
            with cont_p_resultados_ia:
                if 'cat_pres_seleccionada' not in st.session_state:
                    st.session_state['cat_pres_seleccionada'] = None

                if st.session_state['cat_pres_seleccionada']:
                    col_g_p_ia, col_t_p_ia = st.columns(2)
                else:
                    col_g_p_ia = st.container()
                    col_t_p_ia = None

                with col_g_p_ia:
                    evento_p_click = st.plotly_chart(fig_p_ia, use_container_width=True, on_select="rerun")
                
                if evento_p_click and len(evento_p_click["selection"]["points"]) > 0:
                    st.session_state['cat_pres_seleccionada'] = evento_p_click["selection"]["points"][0]["y"]
                else:
                    st.session_state['cat_pres_seleccionada'] = None

                if st.session_state['cat_pres_seleccionada'] and col_t_p_ia is not None:
                    cat_p_actual = st.session_state['cat_pres_seleccionada']
                    ids_p_asociados = res_p.get('Asignaciones', {}).get(cat_p_actual, [])

                    with col_t_p_ia:
                        st.markdown(f"##### 📂 Personal indexado en: {cat_p_actual}")
                        df_p_res_id = df_p_res.set_index('id_prestamo')
                        ids_p_existentes = [idx for idx in ids_p_asociados if idx in df_p_res_id.index]
                        
                        if ids_p_existentes:
                            df_p_detalle = df_p_res_id.loc[ids_p_existentes]
                            st.dataframe(df_p_detalle[['empleado', 'motivo', 'cantidad_autorizada', 'descuento_semanal']], use_container_width=True, hide_index=True, height=280)
                        else:
                            st.warning("Los registros seleccionados no coinciden con los filtros temporales del dashboard.")

# ------------------------------------------
# TAB 3: HORAS EXTRAS
# ------------------------------------------
with tab_horas_extras:
    df_he_raw = dict_rrhh.get("horas_extras", pd.DataFrame())

    if not df_he_raw.empty and f_año:
        df_he_res = df_he_raw[
            (df_he_raw['año'].isin(f_año)) &
            (df_he_raw['mes_nombre'].isin(f_mes)) &
            (df_he_raw['ubicacion'].isin(f_ubi))
        ].copy()
    else:
        df_he_res = pd.DataFrame()

    if not df_he_res.empty:
        # --- METRICAS SUPERIORES HORAS EXTRAS ---
        col_he1, col_he2, col_he3, col_he4 = st.columns(4)

        monto_he_total = df_he_res['total_apagar'].sum()
        total_hrs_dobles = df_he_res['hora_doble'].sum()
        total_hrs_triples = df_he_res['hora_triple'].sum()
        total_registros_he = len(df_he_res)

        with col_he1: 
            st.markdown(create_card("fa-money-bill-wave", "Costo Total A Pagar", f"${monto_he_total:,.2f}"), unsafe_allow_html=True)
        with col_he2:
            st.markdown(create_card("fa-clock", "Horas Dobles", f"{int(total_hrs_dobles)} hrs"), unsafe_allow_html=True)
        with col_he3:
            st.markdown(create_card("fa-business-time", "Horas Triples", f"{int(total_hrs_triples)} hrs"), unsafe_allow_html=True)
        with col_he4:
            st.markdown(create_card("fa-file-signature", "Total Registros", f"{total_registros_he} Órdenes"), unsafe_allow_html=True)
        st.divider()

        # --- GRÁFICAS HORAS EXTRAS ---
        # 1. Top Empleados
        he_emp_data = df_he_res.groupby('empleado').agg(
            monto_total=('total_apagar', 'sum'),
            solicitudes=('id_horaextra', 'count'),
            horas_totales=('total_horas', 'sum')
        ).nlargest(10, 'monto_total').sort_values('monto_total')

        fig_he_empleados = go.Figure(go.Bar(
            y=he_emp_data.index,
            x=he_emp_data['monto_total'],
            orientation='h',
            marker_color='#E63946',
            text=[f"${x:,.2f}" for x in he_emp_data['monto_total']],
            textposition='outside',
            cliponaxis=False,
            # Pasamos un arreglo con [# Solicitudes, Horas Totales] en customdata
            customdata=list(zip(he_emp_data['solicitudes'], he_emp_data['horas_totales'])),
            hovertemplate="👤 <b>Empleado:</b> %{y}<br>" +
                          "📋 <b># Solicitudes:</b> %{customdata[0]} registros<br>" +
                          "⏰ <b>Horas Totales:</b> %{customdata[1]} hrs<br>" +
                          "💰 <b>Pago Total:</b> $%{x:,.2f}<extra></extra>"
        ))

        fig_he_empleados.update_layout(
            title=dict(text="<b>💰 Top 10 Empleados con Mayor Inversión en Horas Extras</b>", font=dict(size=16, color="white")),
            template="plotly_dark",
            margin=dict(l=10, r=130, t=50, b=10),
            xaxis=dict(
                title="Pago Total ($)",
                tickprefix="$",
                range=[0, he_emp_data['monto_total'].max() * 1.35 if not he_emp_data.empty else 1000]
            ),
            yaxis=dict(title="Empleado")
        )

        # 2. Histórico Mensual (Ancho Completo)
        he_hist_data = df_he_res.groupby(['mes_sort', 'mes_nombre']).agg(
            monto_total=('total_apagar', 'sum'),
            horas_dobles=('hora_doble', 'sum'),
            horas_triples=('hora_triple', 'sum')
        ).reset_index()
        
        fig_he_hist = go.Figure()
        fig_he_hist.add_trace(go.Bar(x=he_hist_data['mes_nombre'], y=he_hist_data['horas_dobles'], name="Hrs Dobles", marker_color='#457B9D'))
        fig_he_hist.add_trace(go.Bar(x=he_hist_data['mes_nombre'], y=he_hist_data['horas_triples'], name="Hrs Triples", marker_color='#F4A261'))
        fig_he_hist.add_trace(go.Scatter(x=he_hist_data['mes_nombre'], y=he_hist_data['monto_total'], name="Gasto Total ($)", yaxis="y2", line=dict(color='#E63946', width=3)))
        
        fig_he_hist.update_layout(
            title=dict(text="<b>📅 Flujo Mensual: Volumen de Horas y Gasto Financiero</b>", font=dict(size=16, color="white")),
            template="plotly_dark", barmode='stack', hovermode="x unified",
            yaxis=dict(title="Horas Trabajadas"),
            yaxis2=dict(title="Gasto ($)", overlaying="y", side="right", tickprefix="$"),
            margin=dict(l=10, r=10, t=50, b=10)
        )

        # 3. Top Ubicaciones por Costo
        he_ubi_data = df_he_res.groupby('ubicacion').agg(
            monto_total=('total_apagar', 'sum'),
            total_horas=('total_horas', 'sum')
        ).nlargest(5, 'monto_total').sort_values('monto_total')

        fig_he_ubicaciones = go.Figure(go.Bar(
            y=he_ubi_data.index, x=he_ubi_data['monto_total'], orientation='h', marker_color='#2A9D8F',
            text=[f"${m:,.2f} ({int(h)} hrs)" for h, m in zip(he_ubi_data['total_horas'], he_ubi_data['monto_total'])],
            textposition='outside', customdata=he_ubi_data['total_horas'].values,
            hovertemplate="📍 <b>Ubicación:</b> %{y}<br>💰 <b>Costo Total:</b> $%{x:,.2f}<br>⏰ <b>Horas:</b> %{customdata} hrs<extra></extra>"
        ))
        fig_he_ubicaciones.update_layout(
            title=dict(text="<b>📍 Top 5 Ubicaciones con Mayor Gasto en Horas Extras</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=130, t=50, b=10)
        )

        # 4. Top Responsables que Autorizan
        he_resp_data = df_he_res.groupby('responsable')['total_apagar'].sum().nlargest(5).sort_values()
        fig_he_responsables = go.Figure(go.Bar(
            y=he_resp_data.index, x=he_resp_data.values, orientation='h', marker_color='#E76F51',
            text=[f"${x:,.0f}" for x in he_resp_data.values], textposition='outside'
        ))
        fig_he_responsables.update_layout(
            title=dict(text="<b>👔 Top Responsables por Monto Autorizado en Sobretiempo</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10)
        )

        # --- LIENZO INTERACTIVO HORAS EXTRAS ---
        if 'he_graficas_activas' not in st.session_state:
            st.session_state['he_graficas_activas'] = []
        
        col_he_lienzo, col_he_miniaturas = st.columns([4, 1])

        with col_he_miniaturas:
            st.markdown("<h5 style='text-align: center; color: #FFFFFF;'>📊 Diapositivas</h5>", unsafe_allow_html=True)
            
            btn_he_emp = "primary" if "he_empleados" in st.session_state['he_graficas_activas'] else "secondary"
            if st.button("👥 Costo por Empleado", use_container_width=True, type=btn_he_emp, key="btn_he_emp"):
                if "he_empleados" in st.session_state['he_graficas_activas']: st.session_state['he_graficas_activas'].remove("he_empleados")
                else: st.session_state['he_graficas_activas'].append("he_empleados")
                st.rerun()

            btn_he_his = "primary" if "he_historico" in st.session_state['he_graficas_activas'] else "secondary"
            if st.button("📅 Flujo Mensual", use_container_width=True, type=btn_he_his, key="btn_he_flujo"): # 👈 KEY ÚNICO
                if "he_historico" in st.session_state['he_graficas_activas']: st.session_state['he_graficas_activas'].remove("he_historico")
                else: st.session_state['he_graficas_activas'].append("he_historico")
                st.rerun()

            btn_he_ubi = "primary" if "he_ubicaciones" in st.session_state['he_graficas_activas'] else "secondary"
            if st.button("📍 Top Ubicaciones", use_container_width=True, type=btn_he_ubi, key="btn_he_ubi"):
                if "he_ubicaciones" in st.session_state['he_graficas_activas']: st.session_state['he_graficas_activas'].remove("he_ubicaciones")
                else: st.session_state['he_graficas_activas'].append("he_ubicaciones")
                st.rerun()

            btn_he_resp = "primary" if "he_responsables" in st.session_state['he_graficas_activas'] else "secondary"
            if st.button("👔 Top Responsables", use_container_width=True, type=btn_he_resp, key="btn_he_resp"):
                if "he_responsables" in st.session_state['he_graficas_activas']: st.session_state['he_graficas_activas'].remove("he_responsables")
                else: st.session_state['he_graficas_activas'].append("he_responsables")
                st.rerun()

            st.write("---")
            if st.button("🗑️ Limpiar Pantalla", type="secondary", use_container_width=True, key="btn_he_limpiar"):
                st.session_state['he_graficas_activas'] = []
                st.rerun()

        with col_he_lienzo:
            lista_he = st.session_state['he_graficas_activas']

            if not lista_he:
                st.info("⬅️ Selecciona una o más perspectivas operativas del panel derecho para proyectarlas en el tablero.")
            elif len(lista_he) == 1:
                g = lista_he[0]
                if g == "he_empleados": st.plotly_chart(fig_he_empleados, use_container_width=True, config=config_plotly)
                elif g == "he_historico": st.plotly_chart(fig_he_hist, use_container_width=True, config=config_plotly)
                elif g == "he_ubicaciones": st.plotly_chart(fig_he_ubicaciones, use_container_width=True, config=config_plotly)
                elif g == "he_responsables": st.plotly_chart(fig_he_responsables, use_container_width=True, config=config_plotly)
            else:
                tiene_he_historico = "he_historico" in lista_he
                lista_he_sin_historico = [g for g in lista_he if g != "he_historico"]

                if lista_he_sin_historico:
                    cols_he_render = st.columns(2)
                    for i, g in enumerate(lista_he_sin_historico):
                        with cols_he_render[i % 2]:
                            if g == "he_empleados": st.plotly_chart(fig_he_empleados, use_container_width=True, config=config_plotly)
                            elif g == "he_ubicaciones": st.plotly_chart(fig_he_ubicaciones, use_container_width=True, config=config_plotly)
                            elif g == "he_responsables": st.plotly_chart(fig_he_responsables, use_container_width=True, config=config_plotly)

                if tiene_he_historico:
                    st.plotly_chart(fig_he_hist, use_container_width=True, config=config_plotly)

        # --- SECCIÓN INFERIOR IA HORAS EXTRAS ---
        st.write("---")
        st.markdown("### 🧠 Diagnóstico Operacional de Causales de Sobretiempo (IA)")
        
        col_he_btn_ia, col_he_info_ia = st.columns([1, 3])
        with col_he_btn_ia:
            procesar_he_ia = st.button("🚀 Audit Operacional con Gemini", use_container_width=True)
        with col_he_info_ia:
            st.info("Gemini analiza las justificaciones y motivos de horas extras para identificar si el gasto se debe a picos de producción, fallas de equipo o vacantes.")

        if procesar_he_ia:
            with st.spinner("Auditando causales operativas con Gemini..."):
                resultado_he_rrhh = analizar_motivos_horas_extras_ia(df_he_res)
                if resultado_he_rrhh:
                    st.session_state['res_ia_horas_extras'] = resultado_he_rrhh

        if 'res_ia_horas_extras' in st.session_state:
            res_he = st.session_state['res_ia_horas_extras']
            dict_he_grafica = res_he.get('Categorias', {})
            
            df_he_ia = pd.DataFrame(list(dict_he_grafica.items()), columns=['Causal Operativa', 'Casos']).sort_values('Casos')
            fig_he_ia = px.bar(df_he_ia, x='Casos', y='Causal Operativa', orientation='h', title="🎯 Clasificación Semántica de Justificaciones de Sobretiempo", color_discrete_sequence=['#FFD700'])
            fig_he_ia.update_layout(template="plotly_dark", clickmode='event+select', margin=dict(l=10, r=10, t=50, b=10))

            cont_he_resultados_ia = st.container()
            with cont_he_resultados_ia:
                if 'cat_he_seleccionada' not in st.session_state:
                    st.session_state['cat_he_seleccionada'] = None

                if st.session_state['cat_he_seleccionada']:
                    col_g_he_ia, col_t_he_ia = st.columns(2)
                else:
                    col_g_he_ia = st.container()
                    col_t_he_ia = None

                with col_g_he_ia:
                    evento_he_click = st.plotly_chart(fig_he_ia, use_container_width=True, on_select="rerun")
                
                if evento_he_click and len(evento_he_click["selection"]["points"]) > 0:
                    st.session_state['cat_he_seleccionada'] = evento_he_click["selection"]["points"][0]["y"]
                else:
                    st.session_state['cat_he_seleccionada'] = None

                if st.session_state['cat_he_seleccionada'] and col_t_he_ia is not None:
                    cat_he_actual = st.session_state['cat_he_seleccionada']
                    ids_he_asociados = res_he.get('Asignaciones', {}).get(cat_he_actual, [])

                    with col_t_he_ia:
                        st.markdown(f"##### 📂 Personal indexado en: {cat_he_actual}")
                        df_he_res_id = df_he_res.set_index('id_horaextra')
                        ids_he_existentes = [idx for idx in ids_he_asociados if idx in df_he_res_id.index]
                        
                        if ids_he_existentes:
                            df_he_detalle = df_he_res_id.loc[ids_he_existentes]
                            st.dataframe(df_he_detalle[['empleado', 'responsable', 'motivo', 'total_apagar']], use_container_width=True, hide_index=True, height=280)
                        else:
                            st.warning("Los registros seleccionados no coinciden con los filtros aplicados.")

# ------------------------------------------
# TAB 4: INCAPACIDADES
# ------------------------------------------

# ------------------------------------------
# TAB 5: PERMISOS
# ------------------------------------------
with tab_permisos:
    df_per_raw = dict_rrhh.get("permisos", pd.DataFrame())

    if not df_per_raw.empty and f_año:
        df_per_res = df_per_raw[
            (df_per_raw['año'].isin(f_año)) &
            (df_per_raw['mes_nombre'].isin(f_mes)) &
            (df_per_raw['ubicacion'].isin(f_ubi))
        ].copy()
    else:
        df_per_res = pd.DataFrame()

    if not df_per_res.empty:
        # --- METRICAS SUPERIORES PERMISOS ---
        col_per1, col_per2, col_per3, col_per4 = st.columns(4)

        total_solicitudes_per = len(df_per_res)
        total_horas_per = df_per_res['horas'].sum()

        # 🟢 Cálculo de porcentajes con y sin goce de sueldo
        if total_solicitudes_per > 0:
            permisos_con_goce = len(df_per_res[df_per_res['goce_sueldo'].astype(str).str.upper().str.strip().isin(['SI', '1', 'TRUE', 'S'])])
            permisos_sin_goce = total_solicitudes_per - permisos_con_goce
            
            pct_con_goce = (permisos_con_goce / total_solicitudes_per) * 100
            pct_sin_goce = (permisos_sin_goce / total_solicitudes_per) * 100
        else:
            pct_con_goce = 0.0
            pct_sin_goce = 0.0

        with col_per1: 
            st.markdown(create_card("fa-file-signature", "Total Solicitudes", f"{total_solicitudes_per} Permisos"), unsafe_allow_html=True)
        with col_per2:
            st.markdown(create_card("fa-clock", "Horas Otorgadas", f"{total_horas_per:,.1f} hrs"), unsafe_allow_html=True)
        with col_per3:
            # 🔄 Card 3: % Con Goce de Sueldo
            st.markdown(create_card("fa-user-check", "% Con Goce de Sueldo", f"{pct_con_goce:.1f}%"), unsafe_allow_html=True)
        with col_per4:
            # 🔄 Card 4: % Sin Goce de Sueldo
            st.markdown(create_card("fa-user-xmark", "% Sin Goce de Sueldo", f"{pct_sin_goce:.1f}%"), unsafe_allow_html=True)

        st.divider()

        # --- CONSTRUCCIÓN DE GRÁFICAS ---

        # 1. Top Empleados por Descuento Monetario acumulado y # Permisos
        per_emp_data = df_per_res.groupby('empleado').agg(
            monto_descontado=('monto_descontado', 'sum'),
            dias_descontados=('dias_descontados', 'sum'),
            solicitudes=('id_permiso', 'count')
        ).nlargest(10, 'monto_descontado').sort_values('monto_descontado')

        fig_per_empleados = go.Figure(go.Bar(
            y=per_emp_data.index, 
            x=per_emp_data['monto_descontado'], 
            orientation='h', 
            marker_color='#E63946',
            text=[f"${m:,.2f}" for m in per_emp_data['monto_descontado']],
            textposition='outside',
            cliponaxis=False,
            # Pasamos [# Solicitudes, Días Descontados] en customdata
            customdata=list(zip(per_emp_data['solicitudes'], per_emp_data['dias_descontados'])),
            hovertemplate="👤 <b>Empleado:</b> %{y}<br>" +
                          "💸 <b>Monto Descontado:</b> $%{x:,.2f}<br>" +
                          "📋 <b># Permisos:</b> %{customdata[0]} solicitudes<br>" +
                          "⏳ <b>Días Descontados:</b> %{customdata[1]} días<extra></extra>"
        ))

        fig_per_empleados.update_layout(
            title=dict(text="<b>💰 Top 10 Empleados con Mayor Descuento Monetario por Permisos</b>", font=dict(size=16, color="white")),
            template="plotly_dark", 
            margin=dict(l=10, r=130, t=50, b=10),
            xaxis=dict(
                title="Monto Descontado ($)",
                tickprefix="$",
                range=[0, per_emp_data['monto_descontado'].max() * 1.35 if not per_emp_data.empty else 1000]
            ),
            yaxis=dict(title="Empleado")
        )

        # 2. Flujo Mensual (Eje Dual Mixto) - Solicitudes vs Horas
        per_hist_data = df_per_res.groupby(['mes_sort', 'mes_nombre']).agg(
            solicitudes=('id_permiso', 'count'),
            horas=('horas', 'sum')
        ).reset_index().sort_values('mes_sort')

        fig_per_hist = go.Figure()
        fig_per_hist.add_trace(go.Bar(
            x=per_hist_data['mes_nombre'], y=per_hist_data['solicitudes'],
            name="Solicitudes Registradas", marker_color='#A8DADC',
            hovertemplate="📋 Solicitudes: %{y} permisos<extra></extra>"
        ))
        fig_per_hist.add_trace(go.Scatter(
            x=per_hist_data['mes_nombre'], y=per_hist_data['horas'],
            name="Horas Acumuladas", yaxis="y2", mode='lines+markers',
            line=dict(color='#E63946', width=3), marker=dict(size=8, color='#E63946'),
            hovertemplate="⏰ Horas: %{y:,.1f} hrs<extra></extra>"
        ))
        fig_per_hist.update_layout(
            title=dict(text="<b>📅 Flujo Mensual: Solicitudes de Permiso vs. Horas Otorgadas</b>", font=dict(size=16, color="white")),
            template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Mes"),
            yaxis=dict(title="Número de Solicitudes", showgrid=True),
            yaxis2=dict(title="Horas Acumuladas", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # 3. Tipo de Permisos (Donut)
        per_tipo_data = df_per_res.groupby('tipo_permiso')['id_permiso'].count().reset_index()
        fig_per_tipo = px.pie(
            per_tipo_data, values='id_permiso', names='tipo_permiso',
            title="<b>🏷️ Distribución por Tipo de Permiso</b>",
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_per_tipo.update_layout(template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10))

        # 4. Top Ubicaciones
        per_ubi_data = df_per_res.groupby('ubicacion').agg(
            solicitudes=('id_permiso', 'count'),
            horas=('horas', 'sum')
        ).nlargest(5, 'solicitudes').sort_values('solicitudes')

        fig_per_ubicaciones = go.Figure(go.Bar(
            y=per_ubi_data.index, x=per_ubi_data['solicitudes'], orientation='h', marker_color='#2A9D8F',
            customdata=per_ubi_data['horas'].values,
            hovertemplate="📍 <b>Ubicación:</b> %{y}<br>📋 <b>Solicitudes:</b> %{x}<br>⏰ <b>Horas Totales:</b> %{customdata} hrs<extra></extra>"
        ))
        fig_per_ubicaciones.update_layout(
            title=dict(text="<b>📍 Top 5 Ubicaciones con Mayor Solicitudes de Permiso</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Solicitudes")
        )

        # --- LIENZO INTERACTIVO PERMISOS ---
        if 'per_graficas_activas' not in st.session_state:
            st.session_state['per_graficas_activas'] = []

        col_per_lienzo, col_per_miniaturas = st.columns([4, 1])

        with col_per_miniaturas:
            st.markdown("<h5 style='text-align: center; color: #FFFFFF;'>📊 Diapositivas</h5>", unsafe_allow_html=True)

            btn_per_emp = "primary" if "per_empleados" in st.session_state['per_graficas_activas'] else "secondary"
            if st.button("👥 Solicitudes por Empleado", use_container_width=True, type=btn_per_emp, key="btn_per_emp"):
                if "per_empleados" in st.session_state['per_graficas_activas']: st.session_state['per_graficas_activas'].remove("per_empleados")
                else: st.session_state['per_graficas_activas'].append("per_empleados")
                st.rerun()

            btn_per_his = "primary" if "per_historico" in st.session_state['per_graficas_activas'] else "secondary"
            if st.button("📅 Flujo Mensual", use_container_width=True, type=btn_per_his, key="btn_per_flujo"):
                if "per_historico" in st.session_state['per_graficas_activas']: st.session_state['per_graficas_activas'].remove("per_historico")
                else: st.session_state['per_graficas_activas'].append("per_historico")
                st.rerun()

            btn_per_tipo = "primary" if "per_tipo" in st.session_state['per_graficas_activas'] else "secondary"
            if st.button("🏷️ Tipo de Permiso", use_container_width=True, type=btn_per_tipo, key="btn_per_tipo"):
                if "per_tipo" in st.session_state['per_graficas_activas']: st.session_state['per_graficas_activas'].remove("per_tipo")
                else: st.session_state['per_graficas_activas'].append("per_tipo")
                st.rerun()

            btn_per_ubi = "primary" if "per_ubicaciones" in st.session_state['per_graficas_activas'] else "secondary"
            if st.button("📍 Top Ubicaciones", use_container_width=True, type=btn_per_ubi, key="btn_per_ubi"):
                if "per_ubicaciones" in st.session_state['per_graficas_activas']: st.session_state['per_graficas_activas'].remove("per_ubicaciones")
                else: st.session_state['per_graficas_activas'].append("per_ubicaciones")
                st.rerun()

            st.write("---")
            if st.button("🗑️ Limpiar Pantalla", type="secondary", use_container_width=True, key="btn_per_limpiar"):
                st.session_state['per_graficas_activas'] = []
                st.rerun()

        with col_per_lienzo:
            lista_per = st.session_state['per_graficas_activas']

            if not lista_per:
                st.info("⬅️ Selecciona una o más perspectivas de permisos para proyectarlas en el tablero.")
            elif len(lista_per) == 1:
                g = lista_per[0]
                if g == "per_empleados": st.plotly_chart(fig_per_empleados, use_container_width=True, config=config_plotly)
                elif g == "per_historico": st.plotly_chart(fig_per_hist, use_container_width=True, config=config_plotly)
                elif g == "per_tipo": st.plotly_chart(fig_per_tipo, use_container_width=True, config=config_plotly)
                elif g == "per_ubicaciones": st.plotly_chart(fig_per_ubicaciones, use_container_width=True, config=config_plotly)
            else:
                tiene_per_historico = "per_historico" in lista_per
                lista_per_sin_historico = [g for g in lista_per if g != "per_historico"]

                if lista_per_sin_historico:
                    cols_per_render = st.columns(2)
                    for i, g in enumerate(lista_per_sin_historico):
                        with cols_per_render[i % 2]:
                            if g == "per_empleados": st.plotly_chart(fig_per_empleados, use_container_width=True, config=config_plotly)
                            elif g == "per_tipo": st.plotly_chart(fig_per_tipo, use_container_width=True, config=config_plotly)
                            elif g == "per_ubicaciones": st.plotly_chart(fig_per_ubicaciones, use_container_width=True, config=config_plotly)

                if tiene_per_historico:
                    st.plotly_chart(fig_per_hist, use_container_width=True, config=config_plotly)

        # --- SECCIÓN INFERIOR IA PERMISOS ---
        st.write("---")
        st.markdown("### 🧠 Diagnóstico Semántico de Motivos de Permiso (IA)")
        
        col_per_btn_ia, col_per_info_ia = st.columns([1, 3])
        with col_per_btn_ia:
            procesar_per_ia = st.button("🚀 Diagnosticar con Gemini", use_container_width=True, key="btn_ia_permisos")
        with col_per_info_ia:
            st.info("Gemini clasifica los motivos de permisos registrados para detectar patrones de ausentismo por salud, temas personales o trámites.")

        if procesar_per_ia:
            with st.spinner("Clasificando causas de permisos con Gemini..."):
                resultado_per_rrhh = analizar_motivos_permisos_ia(df_per_res)
                if resultado_per_rrhh:
                    st.session_state['res_ia_permisos'] = resultado_per_rrhh

        if 'res_ia_permisos' in st.session_state:
            res_per = st.session_state['res_ia_permisos']
            dict_per_grafica = res_per.get('Categorias', {})
            
            df_per_ia = pd.DataFrame(list(dict_per_grafica.items()), columns=['Causal de Permiso', 'Casos']).sort_values('Casos')
            fig_per_ia = px.bar(df_per_ia, x='Casos', y='Causal de Permiso', orientation='h', title="🎯 Clasificación Semántica de Solicitudes de Permiso", color_discrete_sequence=['#4EA8DE'])
            fig_per_ia.update_layout(template="plotly_dark", clickmode='event+select', margin=dict(l=10, r=10, t=50, b=10))

            cont_per_resultados_ia = st.container()
            with cont_per_resultados_ia:
                if 'cat_per_seleccionada' not in st.session_state:
                    st.session_state['cat_per_seleccionada'] = None

                if st.session_state['cat_per_seleccionada']:
                    col_g_per_ia, col_t_per_ia = st.columns(2)
                else:
                    col_g_per_ia = st.container()
                    col_t_per_ia = None

                with col_g_per_ia:
                    evento_per_click = st.plotly_chart(fig_per_ia, use_container_width=True, on_select="rerun", key="chart_ia_permisos")
                
                if evento_per_click and len(evento_per_click["selection"]["points"]) > 0:
                    st.session_state['cat_per_seleccionada'] = evento_per_click["selection"]["points"][0]["y"]
                else:
                    st.session_state['cat_per_seleccionada'] = None

                if st.session_state['cat_per_seleccionada'] and col_t_per_ia is not None:
                    cat_per_actual = st.session_state['cat_per_seleccionada']
                    ids_per_asociados = res_per.get('Asignaciones', {}).get(cat_per_actual, [])

                    with col_t_per_ia:
                        st.markdown(f"##### 📂 Personal indexado en: {cat_per_actual}")
                        df_per_res_id = df_per_res.set_index('id_permiso')
                        ids_per_existentes = [idx for idx in ids_per_asociados if idx in df_per_res_id.index]
                        
                        if ids_per_existentes:
                            df_per_detalle = df_per_res_id.loc[ids_per_existentes]
                            st.dataframe(df_per_detalle[['empleado', 'tipo_permiso', 'motivo', 'horas']], use_container_width=True, hide_index=True, height=280)
                        else:
                            st.warning("Los registros seleccionados no coinciden con los filtros aplicados.")


# ------------------------------------------
# TAB 6: SANCIONES
# ------------------------------------------
with tab_sanciones:
    df_san_raw = dict_rrhh.get("sanciones", pd.DataFrame())

    if not df_san_raw.empty and f_año:
        df_san_res = df_san_raw[
            (df_san_raw['año'].isin(f_año)) &
            (df_san_raw['mes_nombre'].isin(f_mes)) &
            (df_san_raw['ubicacion'].isin(f_ubi))
        ].copy()
    else:
        df_san_res = pd.DataFrame()

    if not df_san_res.empty:
        # --- METRICAS SUPERIORES SANCIONES ---
        # --- METRICAS SUPERIORES SANCIONES ---
        col_san1, col_san2, col_san3, col_san4 = st.columns(4)

        total_sanciones = len(df_san_res)
        
        # Normalizamos a mayúsculas y quitamos espacios/acentos
        s_tipo_norm = df_san_res['tipo_sancion'].astype(str).str.upper().str.strip()
        s_consec_norm = df_san_res['consecuencia'].astype(str).str.upper().str.strip()
        
        # 🟢 Búsqueda por "SUSPEN" (Atrapa 'Suspencion', 'Suspensión', 'Suspendido', etc.)
        n_suspension = len(df_san_res[s_consec_norm.str.contains('SUSPEN', na=False)])
        n_reportes = len(df_san_res[s_tipo_norm.str.contains('REPORT', na=False)])
        n_actas = len(df_san_res[s_tipo_norm.str.contains('ACTA', na=False)])

        pct_suspension = (n_suspension / total_sanciones * 100) if total_sanciones > 0 else 0.0
        pct_reportes = (n_reportes / total_sanciones * 100) if total_sanciones > 0 else 0.0
        pct_actas = (n_actas / total_sanciones * 100) if total_sanciones > 0 else 0.0

        with col_san1: 
            st.markdown(create_card("fa-gavel", "Total Sanciones", f"{total_sanciones} Casos"), unsafe_allow_html=True)
        with col_san2:
            st.markdown(create_card("fa-user-clock", "% Suspensión Actividades", f"{pct_suspension:.1f}%"), unsafe_allow_html=True)
        with col_san3:
            st.markdown(create_card("fa-file-exclamation", "% Reportes", f"{pct_reportes:.1f}%"), unsafe_allow_html=True)
        with col_san4:
            st.markdown(create_card("fa-file-signature", "% Actas Administrativas", f"{pct_actas:.1f}%"), unsafe_allow_html=True)

        st.divider()

        # --- CONSTRUCCIÓN DE GRÁFICAS ---

        # 1. Top Empleados con Mayor Número de Sanciones y Descuento Monetario
        san_emp_data = df_san_res.groupby('empleado').agg(
            sanciones=('id_sancion', 'count'),
            monto_descontado=('monto_descontado', 'sum'),
            dias_descontados=('dias_descontados', 'sum')
        ).nlargest(10, 'sanciones').sort_values('sanciones')

        fig_san_empleados = go.Figure(go.Bar(
            y=san_emp_data.index, x=san_emp_data['sanciones'], orientation='h', marker_color='#E63946',
            cliponaxis=False,
            customdata=list(zip(san_emp_data['monto_descontado'], san_emp_data['dias_descontados'])),
            hovertemplate="👤 <b>Empleado:</b> %{y}<br>" +
                          "⚖️ <b># Sanciones:</b> %{x} casos<br>" +
                          "💸 <b>Descuento Estimado:</b> $%{customdata[0]:,.2f}<br>" +
                          "⏳ <b>Días Suspendido:</b> %{customdata[1]} días<extra></extra>"
        ))
        fig_san_empleados.update_layout(
            title=dict(text="<b>👤 Top 10 Empleados con Mayor Número de Sanciones</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Número de Sanciones", range=[0, san_emp_data['sanciones'].max() * 1.25 if not san_emp_data.empty else 10])
        )

        # 2. Flujo Mensual (Eje Dual Mixto) - Sanciones vs Descuento Monetario
        san_hist_data = df_san_res.groupby(['mes_sort', 'mes_nombre']).agg(
            sanciones=('id_sancion', 'count'),
            monto_descontado=('monto_descontado', 'sum')
        ).reset_index().sort_values('mes_sort')

        fig_san_hist = go.Figure()
        fig_san_hist.add_trace(go.Bar(
            x=san_hist_data['mes_nombre'], y=san_hist_data['sanciones'],
            name="Sanciones Aplicadas", marker_color='#F4A261',
            hovertemplate="⚖️ Sanciones: %{y} casos<extra></extra>"
        ))
        fig_san_hist.add_trace(go.Scatter(
            x=san_hist_data['mes_nombre'], y=san_hist_data['monto_descontado'],
            name="Descuento Monetario ($)", yaxis="y2", mode='lines+markers',
            line=dict(color='#E63946', width=3), marker=dict(size=8, color='#E63946'),
            hovertemplate="💸 Retención: $%{y:,.2f}<extra></extra>"
        ))
        fig_san_hist.update_layout(
            title=dict(text="<b>📅 Flujo Mensual: Sanciones vs. Impacto Financiero ($)</b>", font=dict(size=16, color="white")),
            template="plotly_dark", hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Mes"),
            yaxis=dict(title="Número de Sanciones", showgrid=True),
            yaxis2=dict(title="Impacto Financiero ($)", overlaying="y", side="right", tickprefix="$", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # 3. Tipo de Sanción (Donut)
        san_tipo_data = df_san_res.groupby('tipo_sancion')['id_sancion'].count().reset_index()
        fig_san_tipo = px.pie(
            san_tipo_data, values='id_sancion', names='tipo_sancion',
            title="<b>⚖️ Distribución por Tipo de Sanción</b>",
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Dark24
        )

        fig_san_tipo.update_traces(
            textinfo='percent+label', # Muestra porcentaje y nombre (o solo 'percent')
            textfont=dict(size=18, color='white', family='Arial Bold'), # 👈 Aumenta el tamaño del texto a 16px
            insidetextorientation='radial'
        )

        fig_san_tipo.update_layout(
            template="plotly_dark", 
            margin=dict(l=10, r=10, t=50, b=10)
        )

        # 4. Top Ubicaciones por Incidencias Disciplinarias
        san_ubi_data = df_san_res.groupby('ubicacion').agg(
            sanciones=('id_sancion', 'count'),
            monto=('monto_descontado', 'sum')
        ).nlargest(5, 'sanciones').sort_values('sanciones')

        fig_san_ubicaciones = go.Figure(go.Bar(
            y=san_ubi_data.index, x=san_ubi_data['sanciones'], orientation='h', marker_color='#2A9D8F',
            customdata=san_ubi_data['monto'].values,
            hovertemplate="📍 <b>Ubicación:</b> %{y}<br>⚖️ <b>Sanciones:</b> %{x}<br>💸 <b>Descuento Est.:</b> $%{customdata:,.2f}<extra></extra>"
        ))
        fig_san_ubicaciones.update_layout(
            title=dict(text="<b>📍 Top 5 Ubicaciones con Mayor Incidencia Disciplinaria</b>", font=dict(size=16, color="white")),
            template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="Sanciones")
        )

        # --- LIENZO INTERACTIVO SANCIONES ---
        if 'san_graficas_activas' not in st.session_state:
            st.session_state['san_graficas_activas'] = []

        col_san_lienzo, col_san_miniaturas = st.columns([4, 1])

        with col_san_miniaturas:
            st.markdown("<h5 style='text-align: center; color: #FFFFFF;'>📊 Diapositivas</h5>", unsafe_allow_html=True)

            btn_san_emp = "primary" if "san_empleados" in st.session_state['san_graficas_activas'] else "secondary"
            if st.button("👥 Sanciones por Empleado", use_container_width=True, type=btn_san_emp, key="btn_san_emp"):
                if "san_empleados" in st.session_state['san_graficas_activas']: st.session_state['san_graficas_activas'].remove("san_empleados")
                else: st.session_state['san_graficas_activas'].append("san_empleados")
                st.rerun()

            btn_san_his = "primary" if "san_historico" in st.session_state['san_graficas_activas'] else "secondary"
            if st.button("📅 Flujo Mensual", use_container_width=True, type=btn_san_his, key="btn_san_flujo"):
                if "san_historico" in st.session_state['san_graficas_activas']: st.session_state['san_graficas_activas'].remove("san_historico")
                else: st.session_state['san_graficas_activas'].append("san_historico")
                st.rerun()

            btn_san_tipo = "primary" if "san_tipo" in st.session_state['san_graficas_activas'] else "secondary"
            if st.button("⚖️ Tipo de Sanción", use_container_width=True, type=btn_san_tipo, key="btn_san_tipo"):
                if "san_tipo" in st.session_state['san_graficas_activas']: st.session_state['san_graficas_activas'].remove("san_tipo")
                else: st.session_state['san_graficas_activas'].append("san_tipo")
                st.rerun()

            btn_san_ubi = "primary" if "san_ubicaciones" in st.session_state['san_graficas_activas'] else "secondary"
            if st.button("📍 Top Ubicaciones", use_container_width=True, type=btn_san_ubi, key="btn_san_ubi"):
                if "san_ubicaciones" in st.session_state['san_graficas_activas']: st.session_state['san_graficas_activas'].remove("san_ubicaciones")
                else: st.session_state['san_graficas_activas'].append("san_ubicaciones")
                st.rerun()

            st.write("---")
            if st.button("🗑️ Limpiar Pantalla", type="secondary", use_container_width=True, key="btn_san_limpiar"):
                st.session_state['san_graficas_activas'] = []
                st.rerun()

        with col_san_lienzo:
            lista_san = st.session_state['san_graficas_activas']

            if not lista_san:
                st.info("⬅️ Selecciona una o más perspectivas disciplinarias para proyectarlas en el tablero.")
            elif len(lista_san) == 1:
                g = lista_san[0]
                if g == "san_empleados": st.plotly_chart(fig_san_empleados, use_container_width=True, config=config_plotly)
                elif g == "san_historico": st.plotly_chart(fig_san_hist, use_container_width=True, config=config_plotly)
                elif g == "san_tipo": st.plotly_chart(fig_san_tipo, use_container_width=True, config=config_plotly)
                elif g == "san_ubicaciones": st.plotly_chart(fig_san_ubicaciones, use_container_width=True, config=config_plotly)
            else:
                tiene_san_historico = "san_historico" in lista_san
                lista_san_sin_historico = [g for g in lista_san if g != "san_historico"]

                if lista_san_sin_historico:
                    cols_san_render = st.columns(2)
                    for i, g in enumerate(lista_san_sin_historico):
                        with cols_san_render[i % 2]:
                            if g == "san_empleados": st.plotly_chart(fig_san_empleados, use_container_width=True, config=config_plotly)
                            elif g == "san_tipo": st.plotly_chart(fig_san_tipo, use_container_width=True, config=config_plotly)
                            elif g == "san_ubicaciones": st.plotly_chart(fig_san_ubicaciones, use_container_width=True, config=config_plotly)

                if tiene_san_historico:
                    st.plotly_chart(fig_san_hist, use_container_width=True, config=config_plotly)

        # --- SECCIÓN INFERIOR IA SANCIONES ---
        st.write("---")
        st.markdown("### 🧠 Diagnóstico Semántico de Faltas Disciplinarias (IA)")
        
        col_san_btn_ia, col_san_info_ia = st.columns([1, 3])
        with col_san_btn_ia:
            procesar_san_ia = st.button("🚀 Audit Disciplinario con Gemini", use_container_width=True, key="btn_ia_sanciones")
        with col_san_info_ia:
            st.info("Gemini analiza las descripciones y motivos de sanciones para detectar tendencias de faltas operativas, retardos o indisciplina.")

        if procesar_san_ia:
            with st.spinner("Auditando expediente de faltas con Gemini..."):
                resultado_san_rrhh = analizar_motivos_sanciones_ia(df_san_res)
                if resultado_san_rrhh:
                    st.session_state['res_ia_sanciones'] = resultado_san_rrhh

        if 'res_ia_sanciones' in st.session_state:
            res_san = st.session_state['res_ia_sanciones']
            dict_san_grafica = res_san.get('Categorias', {})
            
            df_san_ia = pd.DataFrame(list(dict_san_grafica.items()), columns=['Falta Disciplinaria', 'Casos']).sort_values('Casos')
            fig_san_ia = px.bar(df_san_ia, x='Casos', y='Falta Disciplinaria', orientation='h', title="🎯 Clasificación Semántica de Incidencias Disciplinarias", color_discrete_sequence=['#E76F51'])
            fig_san_ia.update_layout(template="plotly_dark", clickmode='event+select', margin=dict(l=10, r=10, t=50, b=10))

            cont_san_resultados_ia = st.container()
            with cont_san_resultados_ia:
                if 'cat_san_seleccionada' not in st.session_state:
                    st.session_state['cat_san_seleccionada'] = None

                if st.session_state['cat_san_seleccionada']:
                    col_g_san_ia, col_t_san_ia = st.columns(2)
                else:
                    col_g_san_ia = st.container()
                    col_t_san_ia = None

                with col_g_san_ia:
                    evento_san_click = st.plotly_chart(fig_san_ia, use_container_width=True, on_select="rerun", key="chart_ia_sanciones")
                
                if evento_san_click and len(evento_san_click["selection"]["points"]) > 0:
                    st.session_state['cat_san_seleccionada'] = evento_san_click["selection"]["points"][0]["y"]
                else:
                    st.session_state['cat_san_seleccionada'] = None

                if st.session_state['cat_san_seleccionada'] and col_t_san_ia is not None:
                    cat_san_actual = st.session_state['cat_san_seleccionada']
                    ids_san_asociados = res_san.get('Asignaciones', {}).get(cat_san_actual, [])

                    with col_t_san_ia:
                        st.markdown(f"##### 📂 Personal indexado en: {cat_san_actual}")
                        df_san_res_id = df_san_res.set_index('id_sancion')
                        ids_san_existentes = [idx for idx in ids_san_asociados if idx in df_san_res_id.index]
                        
                        if ids_san_existentes:
                            df_san_detalle = df_san_res_id.loc[ids_san_existentes]
                            st.dataframe(df_san_detalle[['empleado', 'tipo_sancion', 'motivo', 'dias_descontados']], use_container_width=True, hide_index=True, height=280)
                        else:
                            st.warning("Los registros seleccionados no coinciden con los filtros aplicados.")

    else:
        st.warning("⚠️ No se encontraron expedientes de sanciones registrados con los filtros seleccionados.")
