
"use strict";

/* =========================================================
   Alza Tu Voz
   Interacciones de la interfaz pública e institucional
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    inicializarMenu();
    inicializarMenuLateral();
    inicializarTema();
    inicializarAnimaciones();
    inicializarVisibilidadContrasenas();
    inicializarNotificaciones();
    actualizarAnio();
});

/* Menú lateral del panel administrativo */
function inicializarMenuLateral() {
    const boton = document.querySelector("[data-sidebar-toggle]");
    const layout = document.querySelector("[data-sidebar-layout]");
    const sidebar = document.querySelector("#admin-sidebar");

    if (!boton || !layout || !sidebar) {
        return;
    }

    function actualizarEstado(cerrado) {
        layout.classList.toggle("is-sidebar-hidden", cerrado);
        boton.setAttribute("aria-expanded", String(!cerrado));
        boton.setAttribute(
            "aria-label",
            cerrado ? "Abrir menú lateral" : "Cerrar menú lateral"
        );
        boton.title = cerrado ? "Abrir menú lateral" : "Cerrar menú lateral";

        const icono = boton.querySelector("i");
        if (icono) {
            icono.className = cerrado ? "bi bi-list" : "bi bi-x-lg";
        }

        try {
            localStorage.setItem(
                "alza-tu-voz-admin-sidebar-hidden",
                String(cerrado)
            );
        } catch (error) {
            console.error("No se pudo guardar el estado del menú lateral.", error);
        }
    }

    let cerrado = false;
    try {
        cerrado =
            localStorage.getItem("alza-tu-voz-admin-sidebar-hidden") === "true";
    } catch (error) {
        console.error("No se pudo leer el estado guardado del menú lateral.", error);
    }
    actualizarEstado(cerrado);

    boton.addEventListener("click", () => {
        actualizarEstado(!layout.classList.contains("is-sidebar-hidden"));
    });
}

/* 0. Tema claro u oscuro */
function inicializarTema() {
    const boton = document.querySelector("[data-theme-toggle]");
    if (!boton) {
        return;
    }

    const raiz = document.documentElement;
    const etiqueta = boton.querySelector(".theme-toggle__label");
    const icono = boton.querySelector("i");
    const metaColor = document.querySelector("#theme-color");

    function aplicarTema(tema, guardar = false) {
        const esOscuro = tema === "dark";
        raiz.dataset.theme = esOscuro ? "dark" : "light";
        boton.setAttribute(
            "aria-label",
            esOscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"
        );
        boton.title = esOscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro";

        if (etiqueta) {
            etiqueta.textContent = esOscuro ? "Modo claro" : "Modo oscuro";
        }
        if (icono) {
            icono.className = esOscuro ? "bi bi-sun" : "bi bi-moon-stars";
        }
        if (metaColor) {
            metaColor.setAttribute("content", esOscuro ? "#10191f" : "#f5f8f6");
        }

        if (guardar) {
            try {
                localStorage.setItem(
                    "alza-tu-voz-theme",
                    esOscuro ? "dark" : "light"
                );
            } catch (error) {
                console.error("No se pudo guardar la preferencia de tema.", error);
            }
        }
    }

    aplicarTema(raiz.dataset.theme === "dark" ? "dark" : "light");
    boton.addEventListener("click", () => {
        aplicarTema(raiz.dataset.theme === "dark" ? "light" : "dark", true);
    });

    window.addEventListener("storage", (evento) => {
        if (evento.key === "alza-tu-voz-theme") {
            aplicarTema(evento.newValue === "dark" ? "dark" : "light");
        }
    });
}

/* 1. Menú de navegación adaptable */
function inicializarMenu() {
    const toggle = document.querySelector(".nav-toggle");
    const navigation = document.querySelector("#site-navigation");

    if (!toggle || !navigation) {
        return;
    }

    const collapse = window.bootstrap?.Collapse?.getOrCreateInstance(
        navigation,
        { toggle: false }
    );
    if (!collapse) {
        return;
    }

    function actualizarToggle(abierto) {
        toggle.setAttribute(
            "aria-label",
            abierto ? "Cerrar menú de navegación" : "Abrir menú de navegación"
        );
        const icono = toggle.querySelector("i");
        if (icono) {
            icono.className = abierto ? "bi bi-x-lg" : "bi bi-list";
        }
    }

    navigation.addEventListener("shown.bs.collapse", () => {
        actualizarToggle(true);
    });
    navigation.addEventListener("hidden.bs.collapse", () => {
        actualizarToggle(false);
    });

    navigation.querySelectorAll("a, button").forEach((enlace) => {
        enlace.addEventListener("click", () => {
            if (window.innerWidth < 992) {
                collapse.hide();
            }
        });
    });

    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape" && navigation.classList.contains("show")) {
            collapse.hide();
            toggle.focus();
        }
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth >= 992 && navigation.classList.contains("show")) {
            collapse.hide();
        }
    });
}

/* 2. Animaciones al entrar los elementos en pantalla */
function inicializarAnimaciones() {
    const elementos = document.querySelectorAll("[data-reveal]");

    if (elementos.length === 0) {
        return;
    }

    /* Respeta la preferencia de movimiento reducido */
    const reducirMovimiento = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    if (
        reducirMovimiento ||
        !("IntersectionObserver" in window)
    ) {
        elementos.forEach((elemento) => {
            elemento.classList.add("is-visible");
        });

        return;
    }

    const observador = new IntersectionObserver(
        (entradas, observer) => {
            entradas.forEach((entrada) => {
                if (entrada.isIntersecting) {
                    entrada.target.classList.add("is-visible");
                    observer.unobserve(entrada.target);
                }
            });
        },
        {
            threshold: 0.12,
            rootMargin: "0px 0px -30px 0px"
        }
    );

    elementos.forEach((elemento, indice) => {
        /* Retraso breve para dar sensación de secuencia */
        elemento.style.transitionDelay =
            `${Math.min(indice % 3, 2) * 90}ms`;

        observador.observe(elemento);
    });
}

/* 3. Mostrar u ocultar contraseñas */
function inicializarVisibilidadContrasenas() {
    document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
        const campo = document.getElementById(
            toggle.getAttribute("data-password-toggle")
        );

        if (!campo) {
            return;
        }

        toggle.addEventListener("click", () => {
            const mostrar = campo.type === "password";
            campo.type = mostrar ? "text" : "password";
            toggle.setAttribute("aria-pressed", String(mostrar));
            toggle.setAttribute(
                "aria-label",
                mostrar ? "Ocultar contraseña" : "Mostrar contraseña"
            );
            const icono = toggle.querySelector("i");
            if (icono) {
                icono.className = mostrar ? "bi bi-eye-slash" : "bi bi-eye";
            }
        });
    });
}

/* 4. Avisos no leídos de la cuenta actual */
function inicializarNotificaciones() {
    const enlace = document.querySelector("[data-notifications-url]");
    const contador = enlace?.querySelector("[data-notification-count]");
    const etiqueta = enlace?.querySelector("[data-notification-label]");

    if (!enlace || !contador || !etiqueta) {
        return;
    }

    fetch(enlace.dataset.notificationsUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
    })
        .then((respuesta) => {
            if (!respuesta.ok) {
                throw new Error(
                    `No se pudieron cargar las notificaciones (${respuesta.status}).`
                );
            }
            return respuesta.json();
        })
        .then((datos) => {
            const cantidad = Number(datos.sin_leer);
            if (!Number.isInteger(cantidad) || cantidad < 0) {
                throw new Error("El servidor devolvió un contador de notificaciones inválido.");
            }
            etiqueta.textContent = cantidad
                ? `Notificaciones, ${cantidad} sin leer`
                : "Notificaciones";
            enlace.setAttribute("aria-label", etiqueta.textContent);
            if (cantidad) {
                contador.textContent = cantidad > 99 ? "99+" : String(cantidad);
                contador.hidden = false;
            }
        })
        .catch((error) => {
            console.error(error);
        });
}

/* 5. Año automático del pie de página */
function actualizarAnio() {
    const elementoAnio = document.querySelector("#current-year");

    if (!elementoAnio) {
        return;
    }

    elementoAnio.textContent = String(new Date().getFullYear());
}
