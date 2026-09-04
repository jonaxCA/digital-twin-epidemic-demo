/* =========================================================================
   Graficas de Highcharts. Una funcion por grafica.
   Cada plantilla llama solo la que necesita.
   ========================================================================= */

const PALETA = {
  primario:  '#1E293B',
  azul:      '#3B82F6',
  critico:   '#DC2626',
  alerta:    '#D97706',
  estable:   '#059669',
  gris:      '#94A3B8',
  borde:     '#E2E8F0',
  texto:     '#64748B',
};

/* Ajustes que comparten todas las graficas: sin logo, tipografia Inter,
   fondo transparente para que herede el color de la tarjeta. */
const BASE = {
  chart: { backgroundColor: 'transparent', style: { fontFamily: 'Inter, sans-serif' } },
  credits: { enabled: false },
  title: { text: null },
  xAxis: { lineColor: PALETA.borde, tickColor: PALETA.borde,
           labels: { style: { color: PALETA.texto, fontSize: '12px' } } },
  yAxis: { gridLineColor: PALETA.borde, title: { text: null },
           labels: { style: { color: PALETA.texto, fontSize: '12px' } } },
  legend: { itemStyle: { color: PALETA.texto, fontWeight: '500', fontSize: '12px' } },
  tooltip: { backgroundColor: '#fff', borderColor: PALETA.borde, borderRadius: 8,
             shadow: false, style: { fontSize: '13px' } },
};

/* Mezcla superficial de opciones sobre BASE. */
function opciones(extra) {
  return Highcharts.merge(BASE, extra);
}


/* --- Dashboard: curva epidemica ------------------------------------------
   Recibe daily_data tal como viene de MongoDB (simulation_daily_series).
-------------------------------------------------------------------------- */
function curvaEpidemica(contenedor, dias) {
  Highcharts.chart(contenedor, opciones({
    chart: { type: 'areaspline', height: 340 },
    xAxis: { categories: dias.map(d => d.date.slice(5)), tickInterval: 4 },
    yAxis: { title: { text: 'Personas' } },
    plotOptions: {
      areaspline: { fillOpacity: 0.14, marker: { enabled: false }, lineWidth: 2 },
    },
    series: [
      { name: 'Casos activos', color: PALETA.azul,
        data: dias.map(d => d.metrics.infected_active) },
      { name: 'Hospitalizados', color: PALETA.alerta,
        data: dias.map(d => d.metrics.hospitalized) },
      { name: 'Defunciones acumuladas', color: PALETA.critico,
        data: dias.map(d => d.metrics.cumulative_deaths) },
    ],
  }));
}


/* --- Monitoreo: evolucion temporal con doble eje -------------------------
   tipo: 'line' | 'column' | 'area' (lo cambian los botones de segmento).
-------------------------------------------------------------------------- */
function evolucionTemporal(contenedor, datos, tipo) {
  tipo = tipo || 'line';

  Highcharts.chart(contenedor, opciones({
    chart: { height: 400 },
    xAxis: { categories: datos.fechas.map(f => f.slice(5)), tickInterval: 3 },
    yAxis: [
      { title: { text: 'Casos confirmados', style: { color: PALETA.azul } } },
      { title: { text: 'Incidencia / 100k' }, opposite: true },
    ],
    plotOptions: { series: { marker: { enabled: tipo === 'line', radius: 3 } } },
    series: [
      { name: 'Casos diarios', type: tipo, color: PALETA.azul,
        fillOpacity: 0.15, data: datos.casos_diarios, yAxis: 0 },
      { name: 'Incidencia acumulada', type: 'line', color: PALETA.primario,
        dashStyle: 'Dot', marker: { enabled: false },
        data: datos.incidencia_acumulada, yAxis: 1 },
    ],
  }));
}


/* --- Monitoreo: barras por grupo etario ---------------------------------- */
function distribucionEtaria(contenedor, grupos) {
  Highcharts.chart(contenedor, opciones({
    chart: { type: 'bar', height: 280 },
    xAxis: { categories: grupos.map(g => g.grupo) },
    yAxis: { title: { text: 'Número de casos' } },
    legend: { enabled: false },
    plotOptions: { bar: { borderRadius: 3, dataLabels: { enabled: true } } },
    series: [{ name: 'Casos', color: PALETA.primario, data: grupos.map(g => g.casos) }],
  }));
}


/* --- Monitoreo: dona por sexo -------------------------------------------- */
function distribucionSexo(contenedor, grupos) {
  Highcharts.chart(contenedor, opciones({
    chart: { type: 'pie', height: 280 },
    plotOptions: {
      pie: {
        innerSize: '62%', borderWidth: 0,
        dataLabels: { style: { fontWeight: '500', fontSize: '12px', textOutline: 'none' },
                      format: '{point.name}: {point.percentage:.1f}%' },
      },
    },
    series: [{
      name: 'Proporción',
      colors: [PALETA.azul, PALETA.primario, PALETA.gris],
      data: grupos.map(g => ({ name: g.nombre, y: g.valor })),
    }],
  }));
}


/* --- Comparacion: simulado contra real ----------------------------------- */
function comparacionReal(contenedor, datos) {
  Highcharts.chart(contenedor, opciones({
    chart: { height: 400 },
    xAxis: { categories: datos.semanas },
    yAxis: { title: { text: 'Número de casos' } },
    series: [
      { name: 'Real', type: 'line', color: PALETA.primario,
        lineWidth: 2.5, marker: { radius: 4 }, data: datos.reales },
      { name: 'Simulación', type: 'line', color: PALETA.azul,
        dashStyle: 'ShortDash', lineWidth: 2,
        marker: { radius: 3 }, data: datos.simulados },
    ],
  }));
}
