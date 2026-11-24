"use strict";

(() => {
    let theme = "light";

    try {
        const savedTheme = localStorage.getItem("alza-tu-voz-theme");
        if (savedTheme === "light" || savedTheme === "dark") {
            theme = savedTheme;
        } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
            theme = "dark";
        }
    } catch {
        theme = "light";
    }

    document.documentElement.dataset.theme = theme;
})();
