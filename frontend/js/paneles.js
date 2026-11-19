// Paneles laterales: predio (F2/F3), cercanos (F3), busqueda (F2) y resumen del municipio (F4).
(function () {
    const { esc, num } = window.UTIL;
    const el = (id) => document.getElementById(id);

    // ---- pestanas -----------------------------------------------------------------
    let activo = "panelPunto";
    window.panelActivo = () => activo;

    document.querySelectorAll(".pestanas button").forEach((b) =>
        b.addEventListener("click", () => {
            activo = b.dataset.panel;
            document.querySelectorAll(".pestanas button").forEach((x) => x.setAttribute("aria-selected", x === b));
            document.querySelectorAll(".contenido").forEach((s) => (s.hidden = s.id !== activo));
            window.seleccion.clearLayers();
            mapa.getContainer().style.cursor = activo === "panelPunto" || activo === "panelCercanos" ? "crosshair" : "";
        })
    );
    mapa.getContainer().style.cursor = "crosshair";

    function mostrar(id, html, clase) {
        const caja = el(id);
        caja.className = "ficha" + (clase ? " " + clase : "");
        caja.innerHTML = html;
    }

    // ---- estado de la conexion ----------------------------------------------------------
    async function estadoBD() {
        const chip = el("estadoBD");
        try {
            const s = await API.salud();
            const v = s.postgresql.split(" ").slice(0, 2).join(" ");
            chip.className = "chip chip-ok";
            chip.textContent = `${v} · PostGIS ${s.postgis.split(" ")[0]} · ${num(s.tablas.terreno)} terrenos`;
            chip.title = `Base: ${s.base}. Filas por tabla: ` + Object.entries(s.tablas).map(([t, n]) => `${t} ${num(n)}`).join(", ");
        } catch (error) {
            chip.className = "chip chip-error";
            chip.textContent = "Sin conexión con la base de datos";
            chip.title = error.message;
            // 404 o respuesta rara: la pagina esta en un hosting estatico, sin API
            const motivo = error.estado === 404 || error.estado === 405
                ? "Esta página se está sirviendo como sitio estático (los endpoints /api no existen aquí)."
                : error.message;
            el("sinServidorMotivo").textContent = motivo;
            el("sinServidor").hidden = false;
        }
    }
    el("btnReintentar").addEventListener("click", () => window.location.reload());

    // ---- F2/F3: ficha de predio ------------------------------------------------------------
    function dibujarPredio(datos) {
        window.seleccion.clearLayers();
        const terreno = L.geoJSON(datos.terreno, { style: { color: "#d50000", weight: 3, fillColor: "#ff8a80", fillOpacity: 0.25 } }).addTo(window.seleccion);
        L.geoJSON(datos.construcciones, { style: { color: "#111", weight: 1.5, fillColor: "#ffd54f", fillOpacity: 0.8 } }).addTo(window.seleccion);
        return terreno.getBounds();
    }

    function fichaHTML(datos) {
        const p = datos.terreno.properties;
        const ubic = p.zona === "U" ? `Manzana ${esc(p.manzana_codigo || "sin asignar")}` : `Vereda ${esc(p.vereda || "sin asignar")}`;
        const filas = datos.construcciones.features.map((f) => {
            const c = f.properties;
            return `<tr><td>${esc(c.identificador || "—")}</td><td>${esc(c.tipo)}</td><td>${c.num_pisos ?? "—"}</td><td>${num(c.area_m2, 1)}</td></tr>`;
        }).join("");
        return `
            <h3>Terreno ${esc(p.codigo)}</h3>
            <dl>
                <dt>Municipio</dt><dd>${esc(p.municipio)} (${esc(p.municipio_codigo)})</dd>
                <dt>Zona</dt><dd>${p.zona === "U" ? "Urbana" : "Rural"} · ${ubic}</dd>
                <dt>Área del terreno</dt><dd>${num(p.area_m2, 1)} m²</dd>
                <dt>Construcciones</dt><dd>${num(p.n_construcciones)} · área construida ${num(p.area_construida_m2, 1)} m² · hasta ${p.max_pisos} piso(s)</dd>
                ${datos.direcciones.length ? `<dt>Direcciones</dt><dd>${datos.direcciones.map(esc).join("<br>")}</dd>` : ""}
            </dl>
            ${filas ? `<table class="tabla"><thead><tr><th>Id.</th><th>Tipo</th><th>Pisos</th><th>m²</th></tr></thead><tbody>${filas}</tbody></table>` : "<p class='ayuda'>Este terreno no tiene construcciones registradas.</p>"}`;
    }

    async function consultarPredio(promesa) {
        mostrar("fichaPredio", "Consultando PostGIS…", "vacio");
        try {
            const datos = await promesa;
            mostrar("fichaPredio", fichaHTML(datos));
            mapa.fitBounds(dibujarPredio(datos), { maxZoom: 19, padding: [40, 40] });
        } catch (error) {
            window.seleccion.clearLayers();
            mostrar("fichaPredio", esc(error.estado === 404 ? error.message : "No se pudo consultar: " + error.message), "vacio");
        }
    }

    // ---- F3: elementos cercanos -------------------------------------------------------------
    el("rngRadio").addEventListener("input", (e) => (el("valRadio").textContent = e.target.value));

    async function consultarCercanos(latlng) {
        const radio = Number(el("rngRadio").value);
        const capa = el("selCapaCercana").value;
        window.seleccion.clearLayers();
        L.circle(latlng, { radius: radio, color: "#111", weight: 1.5, dashArray: "5 4", fillOpacity: 0.04 }).addTo(window.seleccion);
        L.circleMarker(latlng, { radius: 4, color: "#111", fillColor: "#111", fillOpacity: 1 }).addTo(window.seleccion);
        mostrar("resCercanos", "Consultando PostGIS…", "vacio");
        try {
            const datos = await API.cercanos(latlng.lat, latlng.lng, radio, capa);
            L.geoJSON(datos, { style: { color: "#d50000", weight: capa === "vias" ? 3 : 1.5, fillColor: "#ff8a80", fillOpacity: 0.35 } }).addTo(window.seleccion);
            const filas = datos.features.slice(0, 15).map((f) => {
                const p = f.properties;
                const etiqueta = capa === "construcciones" ? `${esc(p.tipo)} · ${p.num_pisos ?? "—"} piso(s)` : capa === "terrenos" ? esc(p.id) : esc(p.nombre || "Vía sin nombre");
                return `<tr><td>${etiqueta}</td><td>${num(p.area_m2 ?? p.longitud_m, 1)}</td><td>${num(p.distancia_m, 1)}</td></tr>`;
            }).join("");
            mostrar("resCercanos",
                `<p><strong>${num(datos.metadatos.total)}</strong> elemento(s) a menos de ${radio} m.${datos.metadatos.total > datos.metadatos.devueltos ? ` Se muestran los ${datos.metadatos.devueltos} más cercanos.` : ""}</p>` +
                (filas ? `<table class="tabla"><thead><tr><th>Elemento</th><th>${capa === "vias" ? "Long. m" : "Área m²"}</th><th>Dist. m</th></tr></thead><tbody>${filas}</tbody></table>` +
                    (datos.features.length > 15 ? "<p class='ayuda'>Se listan los 15 más cercanos; los demás se resaltan en el mapa.</p>" : "") : ""));
        } catch (error) {
            mostrar("resCercanos", esc("No se pudo consultar: " + error.message), "vacio");
        }
    }

    // el clic del mapa lo atiende el panel que este abierto
    window.alClicMapa = (latlng) => {
        if (activo === "panelPunto") consultarPredio(API.terrenoEnPunto(latlng.lat, latlng.lng));
        else if (activo === "panelCercanos") consultarCercanos(latlng);
    };

    // ---- F2: busqueda --------------------------------------------------------------------
    el("formBuscar").addEventListener("submit", async (e) => {
        e.preventDefault();
        const q = el("txtBuscar").value.trim();
        const lista = el("resBusqueda");
        if (q.length < 2) return;
        lista.innerHTML = "<li class='vacio'>Buscando…</li>";
        try {
            const r = await API.buscar(q);
            if (!r.total) {
                lista.innerHTML = "<li class='vacio'>Sin resultados.</li>";
                return;
            }
            lista.innerHTML = r.resultados.map((x, i) =>
                `<li><button type="button" data-i="${i}"><span class="tipo">${esc(x.tipo)}</span><strong>${esc(x.titulo)}</strong><small>${esc(x.detalle)}</small></button></li>`).join("");
            lista.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => irA(r.resultados[b.dataset.i])));
        } catch (error) {
            lista.innerHTML = `<li class='vacio'>${esc(error.message)}</li>`;
        }
    });

    function irA(x) {
        if (x.tipo === "terreno") {
            document.querySelector('[data-panel="panelPunto"]').click();
            consultarPredio(API.terreno(x.id));
        } else {
            mapa.flyTo([x.lat, x.lng], x.tipo === "vereda" ? 14 : 18);
        }
    }

    // ---- F4: resumen del municipio ---------------------------------------------------------------
    function barras(filas, clave, valor) {
        const max = Math.max(...filas.map((f) => f[valor]), 1);
        return filas.map((f) => `<div class="barra-fila"><span>${esc(f[clave])}</span><div class="barra-fondo"><div class="barra-valor" style="width:${(100 * f[valor]) / max}%"></div></div><b>${num(f[valor])}</b></div>`).join("");
    }

    async function resumen(codigo) {
        if (!codigo) return mostrar("resStats", "Elige un municipio o haz clic sobre uno en el mapa.", "vacio");
        mostrar("resStats", "Consultando PostGIS…", "vacio");
        try {
            const d = await API.estadisticas(codigo);
            const r = d.resumen;
            mostrar("resStats", `
                <h3>${esc(r.nombre)}</h3>
                <div class="tarjetas">
                    <div><b>${num(r.terrenos_urbanos)}</b><span>terrenos urbanos</span></div>
                    <div><b>${num(r.terrenos_rurales)}</b><span>terrenos rurales</span></div>
                    <div><b>${num(r.area_urbana_ha, 1)}</b><span>ha urbanas</span></div>
                    <div><b>${num(r.area_rural_ha, 0)}</b><span>ha rurales</span></div>
                    <div><b>${num(r.construcciones)}</b><span>construcciones</span></div>
                    <div><b>${num(r.pisos_promedio, 2)}</b><span>pisos promedio</span></div>
                </div>
                <p class="ayuda">Ocupación construida media de las manzanas: <strong>${num(r.ocupacion_media_manzana * 100, 1)} %</strong></p>
                <h4>Construcciones por tipo</h4>${barras(d.construcciones_por_tipo, "tipo", "cantidad")}
                <h4>Construcciones por número de pisos</h4>${barras(d.construcciones_por_pisos, "pisos", "cantidad")}
                <h4>Manzanas más ocupadas</h4>
                <table class="tabla"><thead><tr><th>Manzana</th><th>Terrenos</th><th>Ocupación</th></tr></thead><tbody>
                ${d.manzanas_mas_ocupadas.map((m) => `<tr><td>${esc(m.codigo)}</td><td>${m.n_terrenos}</td><td>${num(m.indice_ocupacion * 100, 1)} %</td></tr>`).join("")}
                </tbody></table>`);
        } catch (error) {
            mostrar("resStats", esc("No se pudo consultar: " + error.message), "vacio");
        }
    }

    el("selMunicipio").addEventListener("change", (e) => resumen(e.target.value));
    document.addEventListener("click", (e) => {
        const enlace = e.target.closest("[data-resumen]");
        if (!enlace) return;
        e.preventDefault();
        mapa.closePopup();
        el("selMunicipio").value = enlace.dataset.resumen;
        document.querySelector('[data-panel="panelStats"]').click();
        resumen(enlace.dataset.resumen);
    });

    // ---- arranque ------------------------------------------------------------------------------------
    estadoBD();
    cargarMunicipios()
        .then((datos) => {
            el("selMunicipio").innerHTML = "<option value=''>Seleccione…</option>" +
                datos.features.map((f) => `<option value="${esc(f.properties.codigo)}">${esc(f.properties.nombre)}</option>`).join("");
        })
        .catch((error) => window.avisoMapa("No se pudieron cargar los municipios: " + error.message));
})();
