_CATALOGO_TRANSLATION = str.maketrans(
    {
        "¢": "ó",
        "£": "ú",
        "¡": "í",
        "\u00a0": "á",
        "¤": "ñ",
        "¨": "¿",
        "‚": "é",
    }
)


def texto_catalogo(valor):
    return (
        valor.translate(_CATALOGO_TRANSLATION)
        if isinstance(valor, str)
        else valor
    )
