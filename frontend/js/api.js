// Llamadas a los endpoints de la API. Toda la informacion sale de PostgreSQL/PostGIS.
(function () {
    // Si la pagina se abre con Live Server (puerto 5500) la API esta en el 8000
    const puerto = window.location.port;
    const BASE = window.location.protocol === "file:" || puerto === "5500" ? "http://127.0.0.1:8000" : "";

    async function pedir(ruta, parametros) {
        const url = new URL(BASE + ruta, window.location.origin);
        Object.entries(parametros || {}).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
        });
        let respuesta;
        try {
            respuesta = await fetch(url, { signal: AbortSignal.timeout(30000) });
        } catch (error) {
            if (error.name === "AbortError") throw error;
            throw new Error("No se pudo contactar la API. Inicia el servidor con iniciar.bat (Windows) o iniciar.sh.");
        }
        if (!respuesta.ok) {
            let detalle = "";
            try {
                const cuerpo = await respuesta.json();
                detalle = typeof cuerpo.detail === "string" ? cuerpo.detail : "datos de entrada no válidos";
            } catch (e) { /* respuesta sin JSON */ }
            const error = new Error(detalle || `Error HTTP ${respuesta.status}`);
            error.estado = respuesta.status;
            throw error;
        }
        try {
            return await respuesta.json();
        } catch (e) {
            // un hosting estatico devuelve el HTML de la pagina en lugar de JSON
            const error = new Error("La respuesta no es JSON: la API no está disponible en esta dirección.");
            error.estado = 404;
            throw error;
        }
    }

    window.API = {
        salud: () => pedir("/api/salud"),
        municipios: () => pedir("/api/municipios"),
        capa: (capa, bounds, zoom, senal) => {
            const url = new URL(BASE + "/api/capas/" + capa, window.location.origin);
            url.searchParams.set("minx", bounds.getWest().toFixed(6));
            url.searchParams.set("miny", bounds.getSouth().toFixed(6));
            url.searchParams.set("maxx", bounds.getEast().toFixed(6));
            url.searchParams.set("maxy", bounds.getNorth().toFixed(6));
            url.searchParams.set("zoom", Math.round(zoom));
            url.searchParams.set("limite", 5000);
            return fetch(url, { signal: senal }).then(async (r) => {
                if (!r.ok) throw new Error(`Error HTTP ${r.status} al pedir la capa ${capa}`);
                return r.json();
            });
        },
        terrenoEnPunto: (lat, lng) => pedir("/api/terrenos/en-punto", { lat, lng }),
        terreno: (codigo) => pedir("/api/terrenos/" + encodeURIComponent(codigo)),
        cercanos: (lat, lng, radio, capa) => pedir("/api/cercanos", { lat, lng, radio, capa }),
        buscar: (q) => pedir("/api/buscar", { q }),
        estadisticas: (codigo) => pedir("/api/estadisticas/" + codigo),
    };
})();
