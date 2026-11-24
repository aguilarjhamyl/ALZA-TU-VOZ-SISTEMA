"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const ejercicio = document.querySelector("[data-breathing-exercise]");
    if (!ejercicio) {
        return;
    }

    const pulso = ejercicio.querySelector("[data-breathing-pulse]");
    const fase = ejercicio.querySelector("[data-breathing-phase]");
    const temporizador = ejercicio.querySelector("[data-breathing-timer]");
    const iniciar = ejercicio.querySelector("[data-breathing-start]");
    const detener = ejercicio.querySelector("[data-breathing-stop]");
    const duracionTotal = 120;
    let intervalo = null;
    let segundos = 0;
    let faseActual = null;

    function mostrarTiempo(restante) {
        const minutos = Math.floor(restante / 60);
        const segundosRestantes = restante % 60;
        temporizador.textContent =
            `${String(minutos).padStart(2, "0")}:` +
            `${String(segundosRestantes).padStart(2, "0")}`;
    }

    function mostrarFase(segundosTranscurridos) {
        const inhalar = segundosTranscurridos % 10 < 4;
        const siguienteFase = inhalar ? "inhala" : "exhala";
        if (siguienteFase === faseActual) {
            return;
        }
        faseActual = siguienteFase;
        pulso.classList.toggle("is-inhaling", inhalar);
        pulso.classList.toggle("is-exhaling", !inhalar);
        fase.textContent = inhalar ? "Inhala suavemente" : "Exhala suavemente";
    }

    function finalizar(mensaje) {
        window.clearInterval(intervalo);
        intervalo = null;
        faseActual = null;
        pulso.classList.remove("is-inhaling", "is-exhaling");
        fase.textContent = mensaje;
        iniciar.disabled = false;
        detener.disabled = true;
    }

    iniciar.addEventListener("click", () => {
        segundos = 0;
        faseActual = null;
        iniciar.disabled = true;
        detener.disabled = false;
        mostrarFase(segundos);
        mostrarTiempo(duracionTotal);

        intervalo = window.setInterval(() => {
            segundos += 1;
            mostrarTiempo(duracionTotal - segundos);
            if (segundos >= duracionTotal) {
                finalizar("Terminaste. Continúa a tu propio ritmo.");
                return;
            }
            mostrarFase(segundos);
        }, 1000);
    });

    detener.addEventListener("click", () => {
        finalizar("Pausa detenida. Respira con normalidad.");
    });
});
