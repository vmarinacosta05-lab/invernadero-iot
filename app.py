import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------
# Configuración general
# ---------------------------------------------------------------
st.set_page_config(page_title="Invernadero IoT", page_icon="🌱", layout="wide")

CSV_POR_DEFECTO = "datos_invernadero.csv"
ZONA_HORARIA = "America/Bogota"

# Rangos ideales del cultivo (se pueden cambiar en la barra lateral)
TEMP_MIN_DEF, TEMP_MAX_DEF = 20.0, 28.0   # °C
HUM_MIN_DEF, HUM_MAX_DEF = 40.0, 70.0     # % de humedad del suelo


# ---------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------
def cargar_datos(origen):
    """Lee el CSV exportado de Grafana y deja la hora en zona horaria local."""
    df = pd.read_csv(origen)

    faltan = {"time", "temp", "hum_suelo"} - set(df.columns)
    if faltan:
        st.error(f"Al archivo le faltan estas columnas: {', '.join(sorted(faltan))}")
        st.stop()

    # Grafana exporta la hora como milisegundos desde 1970
    if pd.api.types.is_numeric_dtype(df["time"]):
        unidad = "ms" if df["time"].abs().max() > 1e11 else "s"
        hora = pd.to_datetime(df["time"], unit=unidad, utc=True)
    else:
        hora = pd.to_datetime(df["time"], utc=True)

    df["hora"] = hora.dt.tz_convert(ZONA_HORARIA)
    df = df.dropna(subset=["temp", "hum_suelo"]).sort_values("hora")
    return df.reset_index(drop=True)


def grafico_serie(df, columna, titulo, unidad, minimo, maximo, color):
    """Línea de tiempo con la franja del rango ideal y las lecturas fuera de rango."""
    fig = go.Figure()
    fig.add_hrect(
        y0=minimo, y1=maximo, fillcolor="green", opacity=0.12, line_width=0,
        annotation_text="Rango ideal", annotation_position="top left",
    )
    fig.add_trace(go.Scatter(
        x=df["hora"], y=df[columna], mode="lines+markers",
        name=titulo, line=dict(color=color),
    ))
    fuera = df[(df[columna] < minimo) | (df[columna] > maximo)]
    fig.add_trace(go.Scatter(
        x=fuera["hora"], y=fuera[columna], mode="markers",
        name="Fuera de rango", marker=dict(color="red", size=11, symbol="x"),
    ))
    fig.update_layout(
        title=titulo, yaxis_title=unidad, xaxis_title="Hora",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.25),
    )
    return fig


def describir_correlacion(r):
    fuerza = abs(r)
    if fuerza < 0.3:
        nivel = "muy débil o nula"
    elif fuerza < 0.5:
        nivel = "débil"
    elif fuerza < 0.7:
        nivel = "moderada"
    else:
        nivel = "fuerte"
    if fuerza < 0.3:
        return f"La relación es {nivel}: la temperatura y la humedad del suelo no parecen moverse juntas."
    sentido = (
        "cuando sube la temperatura, la humedad del suelo tiende a subir"
        if r > 0 else
        "cuando sube la temperatura, la humedad del suelo tiende a bajar"
    )
    return f"La relación es {nivel} y {'positiva' if r > 0 else 'negativa'}: {sentido}."


# ---------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------
st.title("🌱 Monitoreo del invernadero")
st.caption(
    "Datos de temperatura del invernadero (°C) y humedad del suelo (%) medidos con un "
    "ESP32 simulado en Wokwi, enviados por MQTT a ThingsBoard y guardados en InfluxDB."
)

# ---------------------------------------------------------------
# Barra lateral: datos y rangos ideales
# ---------------------------------------------------------------
st.sidebar.header("⚙️ Configuración")

archivo = st.sidebar.file_uploader("Sube otro CSV (opcional)", type="csv")
st.sidebar.caption("Si no subes nada, se usa el archivo incluido en la app.")

st.sidebar.subheader("Rangos ideales del cultivo")
temp_min, temp_max = st.sidebar.slider(
    "Temperatura ideal (°C)", 0.0, 50.0, (TEMP_MIN_DEF, TEMP_MAX_DEF), step=0.5
)
hum_min, hum_max = st.sidebar.slider(
    "Humedad del suelo ideal (%)", 0.0, 100.0, (HUM_MIN_DEF, HUM_MAX_DEF), step=1.0
)

df = cargar_datos(archivo if archivo is not None else CSV_POR_DEFECTO)

if df.empty:
    st.warning("El archivo no tiene lecturas válidas.")
    st.stop()

# ---------------------------------------------------------------
# Marcar lecturas fuera de rango
# ---------------------------------------------------------------
df["temp_alerta"] = np.select(
    [df["temp"] < temp_min, df["temp"] > temp_max],
    ["Frío", "Calor"], default="Normal",
)
df["hum_alerta"] = np.select(
    [df["hum_suelo"] < hum_min, df["hum_suelo"] > hum_max],
    ["Suelo seco", "Suelo encharcado"], default="Normal",
)
df["en_rango"] = (df["temp_alerta"] == "Normal") & (df["hum_alerta"] == "Normal")

# ---------------------------------------------------------------
# 1. Resumen
# ---------------------------------------------------------------
st.header("1. Resumen general")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Lecturas analizadas", len(df))
c2.metric("Temperatura promedio", f"{df['temp'].mean():.1f} °C")
c3.metric("Humedad del suelo promedio", f"{df['hum_suelo'].mean():.1f} %")
c4.metric("Lecturas con todo en rango", f"{df['en_rango'].mean() * 100:.0f} %")

st.caption(
    f"Periodo: {df['hora'].min():%d/%m/%Y %H:%M:%S} a {df['hora'].max():%d/%m/%Y %H:%M:%S} "
    f"(hora de Colombia)"
)

# ---------------------------------------------------------------
# 2. Estadísticas
# ---------------------------------------------------------------
st.header("2. Estadísticas por variable")

estadisticas = pd.DataFrame({
    "Temperatura del invernadero (°C)": df["temp"].describe(),
    "Humedad del suelo (%)": df["hum_suelo"].describe(),
}).rename(index={
    "count": "Lecturas", "mean": "Promedio", "std": "Desviación estándar",
    "min": "Mínimo", "25%": "Percentil 25", "50%": "Mediana",
    "75%": "Percentil 75", "max": "Máximo",
})
st.dataframe(estadisticas.round(2))

# ---------------------------------------------------------------
# 3. Gráficos con rango ideal
# ---------------------------------------------------------------
st.header("3. Evolución en el tiempo")
g1, g2 = st.columns(2)
g1.plotly_chart(
    grafico_serie(df, "temp", "Temperatura del invernadero", "°C", temp_min, temp_max, "#e4572e"),
)
g2.plotly_chart(
    grafico_serie(df, "hum_suelo", "Humedad del suelo", "%", hum_min, hum_max, "#2e86ab"),
)

# ---------------------------------------------------------------
# 4. Alertas por umbral
# ---------------------------------------------------------------
st.header("4. Alertas por umbral")

n_temp = int((df["temp_alerta"] != "Normal").sum())
n_hum = int((df["hum_alerta"] != "Normal").sum())

a1, a2 = st.columns(2)
with a1:
    if n_temp:
        st.error(
            f"🌡️ La temperatura salió del rango ({temp_min:g}–{temp_max:g} °C) "
            f"en {n_temp} de {len(df)} lecturas."
        )
    else:
        st.success(f"🌡️ La temperatura se mantuvo dentro de {temp_min:g}–{temp_max:g} °C.")
with a2:
    if n_hum:
        st.error(
            f"💧 La humedad del suelo salió del rango ({hum_min:g}–{hum_max:g} %) "
            f"en {n_hum} de {len(df)} lecturas."
        )
    else:
        st.success(f"💧 La humedad del suelo se mantuvo dentro de {hum_min:g}–{hum_max:g} %.")

alertas = df[~df["en_rango"]][["hora", "temp", "temp_alerta", "hum_suelo", "hum_alerta"]].rename(
    columns={
        "hora": "Hora", "temp": "Temperatura (°C)", "temp_alerta": "Estado temperatura",
        "hum_suelo": "Humedad del suelo (%)", "hum_alerta": "Estado humedad",
    }
)
if not alertas.empty:
    with st.expander(f"Ver las {len(alertas)} lecturas con alerta"):
        st.dataframe(alertas, hide_index=True)

# Recomendación según la última lectura (conecta con el actuador del proyecto)
ultima = df.iloc[-1]
st.subheader("Estado de la última lectura")
st.write(
    f"Última lectura ({ultima['hora']:%H:%M:%S}): **{ultima['temp']:.1f} °C** "
    f"y **{ultima['hum_suelo']:.1f} %** de humedad del suelo."
)
if ultima["hum_alerta"] == "Suelo seco":
    st.warning("💧 El suelo está seco: conviene **encender la bomba de riego**.")
elif ultima["hum_alerta"] == "Suelo encharcado":
    st.warning("💧 El suelo está encharcado: conviene **mantener apagada la bomba de riego**.")
if ultima["temp_alerta"] == "Calor":
    st.warning("🌡️ Hace demasiado calor en el invernadero: conviene ventilar.")
elif ultima["temp_alerta"] == "Frío":
    st.warning("🌡️ Hace demasiado frío en el invernadero: conviene abrigar el cultivo.")
if ultima["en_rango"]:
    st.success("✅ Las dos variables están dentro del rango ideal.")

# ---------------------------------------------------------------
# 5. Correlación
# ---------------------------------------------------------------
st.header("5. Correlación entre temperatura y humedad del suelo")

if len(df) >= 3 and df["temp"].nunique() > 1 and df["hum_suelo"].nunique() > 1:
    r = df["temp"].corr(df["hum_suelo"])

    col_r, col_g = st.columns([1, 2])
    with col_r:
        st.metric("Coeficiente de correlación (r)", f"{r:.2f}")
        st.write(describir_correlacion(r))
        if len(df) < 30:
            st.info(
                f"Hay solo {len(df)} lecturas. Con tan pocos datos la correlación "
                "es poco confiable: conviene recolectar más."
            )
        st.caption("Correlación no implica causalidad.")
    with col_g:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["temp"], y=df["hum_suelo"], mode="markers", name="Lecturas",
            marker=dict(size=10, color="#6a4c93"),
        ))
        pendiente, intercepto = np.polyfit(df["temp"], df["hum_suelo"], 1)
        xs = np.array([df["temp"].min(), df["temp"].max()])
        fig.add_trace(go.Scatter(
            x=xs, y=pendiente * xs + intercepto, mode="lines",
            name="Tendencia", line=dict(color="gray", dash="dash"),
        ))
        fig.update_layout(
            xaxis_title="Temperatura (°C)", yaxis_title="Humedad del suelo (%)",
            margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.25),
        )
        st.plotly_chart(fig)
else:
    st.info("Se necesitan al menos 3 lecturas con valores distintos para calcular la correlación.")

# ---------------------------------------------------------------
# 6. Datos
# ---------------------------------------------------------------
st.header("6. Datos")
tabla = df[["hora", "temp", "hum_suelo"]].rename(columns={
    "hora": "Hora", "temp": "Temperatura (°C)", "hum_suelo": "Humedad del suelo (%)",
})
st.dataframe(tabla, hide_index=True)
st.download_button(
    "⬇️ Descargar datos en CSV",
    tabla.to_csv(index=False).encode("utf-8"),
    file_name="datos_invernadero_analizados.csv",
    mime="text/csv",
)
