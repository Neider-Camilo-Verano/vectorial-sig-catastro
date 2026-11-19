// Mapa Leaflet: capas base, capas catastrales cargadas por ventana y leyenda.
(function () {
    const CENTRO = [4.5339, -75.6811];
    const map = L.map("mapa", { zoomControl: true }).setView(CENTRO, 10);
    window.mapa = map;

    // ---- mapas base -------------------------------------------------
    const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        referrerPolicy: "origin", // OpenStreetMap exige indicar la pagina de origen
        attribution: "© colaboradores de <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>",
    }).addTo(map);
    const satelite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19,
        attribution: "Imágenes © Esri, Maxar, Earthstar Geographics",
    });

    // ---- utilidades ---------------------------------------------------
    const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const num = (n, d = 0) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-CO", { maximumFractionDigits: d }));
    window.UTIL = { esc, num };

    function aviso(texto) {
        const caja = document.getElementById("avisoMapa");
        caja.textContent = texto || "";
        caja.hidden = !texto;
    }
    window.avisoMapa = aviso;

    // ---- estilos --------------------------------------------------------
    const ESCALA_OCUPACION = [
        [0.25, "#fff3b0", "menos de 25 %"],
        [0.5, "#fdbf6f", "25 – 50 %"],
        [0.75, "#f4793b", "50 – 75 %"],
        [1.0, "#d7301f", "75 – 100 %"],
        [Infinity, "#7f0000", "más de 100 %"],
    ];
    const colorOcupacion = (v) => (v === null || v === undefined ? "#cccccc" : ESCALA_OCUPACION.find(([max]) => v < max)[1]);

    const COLOR_PISOS = { 0: "#9e9e9e", 1: "#6baed6", 2: "#3182bd", 3: "#08519c", 4: "#08306b" };
    const colorPisos = (p) => COLOR_PISOS[Math.min(p || 0, 4)];

    // ---- capas catastrales ------------------------------------------------
    // zoomMin: nivel desde el que se pide la capa (evita traer miles de poligonos)
    const CAPAS = {
        veredas: {
            nombre: "Veredas", zoomMin: 10,
            estilo: () => ({ color: "#2e7d32", weight: 1.2, dashArray: "4 3", fillColor: "#a5d6a7", fillOpacity: 0.12 }),
            popup: (p) => `<strong>Vereda ${esc(p.nombre)}</strong><br>Código: ${esc(p.id)}<br>Área: ${num(p.area_m2 / 10000, 1)} ha`,
        },
        perimetros: {
            nombre: "Perímetros urbanos", zoomMin: 10,
            estilo: () => ({ color: "#6a1b9a", weight: 2, fillColor: "#ce93d8", fillOpacity: 0.1 }),
            popup: (p) => `<strong>Perímetro urbano ${esc(p.nombre)}</strong><br>Área: ${num(p.area_m2 / 10000, 1)} ha`,
        },
        manzanas: {
            nombre: "Manzanas (ocupación construida)", zoomMin: 14, leyenda: true,
            estilo: (f) => ({ color: "#333", weight: 0.7, fillColor: colorOcupacion(f.properties.indice_ocupacion), fillOpacity: 0.65 }),
            popup: (p) => `<strong>Manzana ${esc(p.id)}</strong><br>Terrenos: ${num(p.n_terrenos)}<br>Construcciones: ${num(p.n_construcciones)}<br>Ocupación construida: ${num((p.indice_ocupacion || 0) * 100, 1)} %`,
        },
        terrenos: {
            nombre: "Terrenos (predios)", zoomMin: 16,
            estilo: (f) => ({ color: f.properties.zona === "U" ? "#1565c0" : "#558b2f", weight: 1, fillColor: "#ffffff", fillOpacity: 0.05 }),
            popup: (p) => `<strong>Terreno ${esc(p.id)}</strong><br>Zona: ${p.zona === "U" ? "urbana" : "rural"}<br>Área: ${num(p.area_m2, 1)} m²`,
        },
        construcciones: {
            nombre: "Construcciones", zoomMin: 17, leyenda: true,
            estilo: (f) => ({ color: "#222", weight: 0.6, fillColor: colorPisos(f.properties.num_pisos), fillOpacity: 0.7 }),
            popup: (p) => `<strong>Construcción</strong> (${esc(p.tipo)})<br>Pisos: ${p.num_pisos ?? "sin dato"}<br>Área: ${num(p.area_m2, 1)} m²<br>Terreno: ${esc(p.terreno_codigo || "sin asociar")}`,
        },
        vias: {
            nombre: "Nomenclatura vial", zoomMin: 14,
            estilo: () => ({ color: "#e65100", weight: 2.2 }),
            popup: (p) => `<strong>${esc(p.nombre || "Vía sin nombre")}</strong><br>Longitud: ${num(p.longitud_m, 0)} m`,
        },
    };

    const grupos = {};
    const controles = {};
    const pendientes = {};
    // en los tooltips el detalle va en una linea compacta

    Object.entries(CAPAS).forEach(([clave, cfg]) => {
        grupos[clave] = L.layerGroup();
        controles[`${cfg.nombre} <small>(zoom ≥ ${cfg.zoomMin})</small>`] = grupos[clave];
    });

    // municipios: se cargan una vez y siempre se muestran
    const grupoMunicipios = L.layerGroup().addTo(map);
    const capaMunicipios = { geojson: null };

    L.control.layers({ "OpenStreetMap": osm, "Satélite (Esri)": satelite }, { "Municipios": grupoMunicipios, ...controles }, { collapsed: true }).addTo(map);

    async function cargarCapa(clave) {
        const cfg = CAPAS[clave];
        const grupo = grupos[clave];
        if (!map.hasLayer(grupo)) return;
        if (map.getZoom() < cfg.zoomMin) {
            grupo.clearLayers();
            return;
        }
        pendientes[clave]?.abort();
        const control = (pendientes[clave] = new AbortController());
        try {
            const datos = await API.capa(clave, map.getBounds(), map.getZoom(), control.signal);
            grupo.clearLayers();
            L.geoJSON(datos, {
                style: cfg.estilo,
                pointToLayer: undefined,
                // el detalle se ve al pasar el cursor; el clic lo usa el panel (predio / cercanos)
                onEachFeature: (f, capa) => capa.bindTooltip(cfg.popup(f.properties), { sticky: true }),
            }).addTo(grupo);
            if (datos.metadatos?.truncado) aviso(`La capa «${cfg.nombre}» muestra solo los primeros ${datos.metadatos.limite} elementos de esta ventana. Acerca el mapa para ver el resto.`);
        } catch (error) {
            if (error.name !== "AbortError") aviso("No se pudo cargar «" + cfg.nombre + "»: " + error.message);
        }
        actualizarLeyenda();
    }

    function cargarTodas() {
        aviso("");
        Object.keys(CAPAS).forEach(cargarCapa);
    }

    let temporizador;
    map.on("moveend", () => {
        clearTimeout(temporizador);
        temporizador = setTimeout(cargarTodas, 250); // espera a que termine de moverse
    });
    map.on("overlayadd", (e) => {
        const clave = Object.keys(grupos).find((k) => grupos[k] === e.layer);
        if (clave) cargarCapa(clave);
        actualizarLeyenda();
    });
    map.on("overlayremove", actualizarLeyenda);

    // ---- leyenda ------------------------------------------------------------
    function actualizarLeyenda() {
        const caja = document.getElementById("leyenda");
        let html = "";
        if (map.hasLayer(grupos.manzanas) && map.getZoom() >= CAPAS.manzanas.zoomMin) {
            html += "<strong>Ocupación construida de la manzana</strong>";
            html += ESCALA_OCUPACION.map(([, c, t]) => `<div><i style="background:${c}"></i>${t}</div>`).join("");
        }
        if (map.hasLayer(grupos.construcciones) && map.getZoom() >= CAPAS.construcciones.zoomMin) {
            html += "<strong>Pisos de la construcción</strong>";
            html += [["0", "sin dato"], ["1", "1 piso"], ["2", "2 pisos"], ["3", "3 pisos"], ["4", "4 o más"]]
                .map(([k, t]) => `<div><i style="background:${COLOR_PISOS[k]}"></i>${t}</div>`).join("");
        }
        caja.innerHTML = html;
        caja.hidden = !html;
    }
    map.on("zoomend", actualizarLeyenda);

    // ---- municipios (F1) ---------------------------------------------------------
    window.cargarMunicipios = async function () {
        const datos = await API.municipios();
        capaMunicipios.geojson = L.geoJSON(datos, {
            style: { color: "#111", weight: 2, fillColor: "#ffffff", fillOpacity: 0.02 },
            onEachFeature: (f, capa) => {
                const p = f.properties;
                capa.bindTooltip(esc(p.nombre), { sticky: true });
                capa.bindPopup(
                    `<strong>${esc(p.nombre)}</strong> (${esc(p.codigo)})<br>Área: ${num(p.area_km2, 1)} km²<br>` +
                    `Manzanas: ${num(p.n_manzanas)} · Veredas: ${num(p.n_veredas)}<br>` +
                    `Terrenos: ${num(p.n_terrenos)} · Construcciones: ${num(p.n_construcciones)}<br>` +
                    `<a href="#" data-resumen="${esc(p.codigo)}">Ver resumen del municipio</a>`
                );
            },
        }).addTo(grupoMunicipios);
        map.fitBounds(capaMunicipios.geojson.getBounds().pad(0.05));
        return datos;
    };

    // ---- resaltado de la seleccion (predio, cercanos) -------------------------------
    const seleccion = L.layerGroup().addTo(map);
    window.seleccion = seleccion;

    // ---- clic en el mapa: lo atiende el panel activo ------------------------------------
    map.on("click", (e) => window.alClicMapa && window.alClicMapa(e.latlng));

    cargarTodas();
})();
